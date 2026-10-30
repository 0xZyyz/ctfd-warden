from datetime import datetime

import sqlalchemy as sa
from flask import render_template, request

from CTFd.models import Challenges, Flags, Teams, Tokens, Users, db
from CTFd.utils.decorators import admins_only

from . import accounts, blocks, fastsolves, honeypots, settings, sharing
from .common import blueprint, handle_removal, teams_mode, template
from .filters import Filters
from .models import ClientEvent, DeviceSession, FlagShare, HoneypotHit, LockoutEvent


def _feature_rows():
    return [
        {
            "name": name,
            "title": title,
            "description": description,
            "enabled": settings.enabled(name),
            "forced": settings.env_override(name) is not None,
        }
        for name, (_, title, description) in settings.FEATURES.items()
    ]


def _int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _account_label(key):
    kind, account_id = key[:1], _int(key[1:])
    current = (kind == "t") == teams_mode()
    if kind == "t":
        team = Teams.query.filter_by(id=account_id).first()
        name = team.name if team else f"Deleted team #{account_id}"
        if current:
            return name, "warden.account", {"account_id": account_id}
        return name, "admin.teams_detail", {"team_id": account_id}
    user = Users.query.filter_by(id=account_id).first()
    name = user.name if user else f"Deleted user #{account_id}"
    if current:
        return name, "warden.account", {"account_id": account_id}
    return name, "admin.users_detail", {"user_id": account_id}


def _members(filters):
    if not (teams_mode() and filters["player"]):
        return {}
    out = {}
    for user_id, team_id in db.session.query(Users.id, Users.team_id):
        out.setdefault(team_id, []).append(user_id)
    return out


def _lookup(model, ids):
    ids = {i for i in ids if i}
    return {row.id: row for row in model.query.filter(model.id.in_(ids)).all()} if ids else {}


def _handle_post():
    action = request.form.get("action")
    if action == "features":
        for name in settings.FEATURES:
            if settings.env_override(name) is None:
                settings.set_enabled(name, request.form.get(name) == "on")
        return "Features saved."
    if action == "lock-settings":
        values = {k: _int(request.form.get(k)) for k in settings.LOCK_DEFAULTS}
        if any(v is None or v < settings.LOCK_MINIMUMS[k] for k, v in values.items()):
            return (
                "Lockout settings not saved: use whole numbers "
                "(threshold >= 5, window and duration >= 60 seconds)."
            )
        settings.save_lock_settings(values)
        return "Lockout settings saved."
    if action == "remove-lockout":
        LockoutEvent.query.filter_by(id=request.form.get("id", "")).delete(
            synchronize_session=False
        )
        db.session.commit()
        return "Lockout entry removed."
    if action == "clear-lockouts":
        n = LockoutEvent.query.delete(synchronize_session=False)
        db.session.commit()
        return f"Removed all {n} lockout entries."
    if action == "add-block":
        challenge_id = _int(request.form.get("challenge_id"))
        account_id = _int(request.form.get("account_id"))
        model = Teams if teams_mode() else Users
        if not Challenges.query.filter_by(id=challenge_id).first():
            return "No challenge with that ID."
        if not model.query.filter_by(id=account_id).first():
            return f"No {'team' if teams_mode() else 'user'} with that ID."
        blocks.add_block(challenge_id, f"{'t' if teams_mode() else 'u'}{account_id}")
        return "Challenge blocked for that account."
    if action == "remove-block":
        blocks.remove_block(
            _int(request.form.get("challenge_id")) or 0, request.form.get("account", "")
        )
        return "Block removed."
    return None


@blueprint.route("/admin/warden", methods=["GET", "POST"])
@admins_only
def overview():
    message = _handle_post() if request.method == "POST" else None
    filters = Filters()

    lockouts = (
        filters.query(
            LockoutEvent.query,
            users=(LockoutEvent.user_id,),
            teams=(LockoutEvent.team_id,),
            challenges=(LockoutEvent.challenge_id,),
            ips=(LockoutEvent.ip,),
        )
        .order_by(LockoutEvent.date.desc())
        .limit(200)
        .all()
    )
    for e in lockouts:
        e.team = Teams.query.get(e.team_id) if e.team_id else None
        e.user = Users.query.get(e.user_id) if e.user_id else None
        e.challenge = Challenges.query.get(e.challenge_id) if e.challenge_id else None

    challenge_names = dict(db.session.query(Challenges.id, Challenges.name).all())
    block_rows = []
    members = _members(filters)
    for challenge_id, keys in sorted(blocks.load_blocks().items()):
        for account in sorted(keys):
            account_id = _int(account[1:])
            if account.startswith("t"):
                team_ids, user_ids = [account_id], members.get(account_id, [])
            else:
                team_ids, user_ids = [], [account_id]
            if not filters.keep(user_ids, team_ids, [challenge_id], ips=None):
                continue
            name, endpoint, args = _account_label(account)
            block_rows.append(
                {
                    "challenge_id": challenge_id,
                    "challenge": challenge_names.get(challenge_id, f"#{challenge_id}"),
                    "account": account,
                    "name": name,
                    "endpoint": endpoint,
                    "args": args,
                }
            )

    return render_template(
        template("admin_overview.html"),
        message=message,
        features=_feature_rows(),
        enabled={name: settings.enabled(name) for name in settings.FEATURES},
        lock=settings.lock_settings(),
        lockouts=lockouts,
        blocks=block_rows,
        challenges=sorted(challenge_names.items(), key=lambda c: c[1].lower()),
        teams_mode=teams_mode(),
        filters=filters,
    )


@blueprint.route("/admin/warden/activity", methods=["GET", "POST"])
@admins_only
def activity():
    message = None
    if request.method == "POST" and request.form.get("action") in (
        "revoke-token",
        "revoke-all-tokens",
    ):
        query = Tokens.query.filter(
            Tokens.user_id.in_(db.session.query(Users.id).filter(Users.type != "admin"))
        )
        if request.form.get("action") == "revoke-token":
            query = query.filter(Tokens.id == request.form.get("id", ""))
        count = query.delete(synchronize_session=False)
        db.session.commit()
        message = f"Revoked {count} token(s)."
    else:
        message = handle_removal(ClientEvent)

    filters = Filters(("player", "team", "ip"))
    query = filters.query(
        ClientEvent.query,
        users=(ClientEvent.user_id,),
        teams=(ClientEvent.team_id,),
        ips=(ClientEvent.ip,),
    )
    kind = request.args.get("kind", "")
    if kind in ("ai", "api-token", "automation"):
        query = query.filter_by(kind=kind)
    user_id = request.args.get("user_id", type=int)
    if user_id:
        query = query.filter_by(user_id=user_id)
    pagination = query.order_by(ClientEvent.id.desc()).paginate(
        page=max(1, request.args.get("page", 1, type=int)), per_page=100, error_out=False
    )
    events = pagination.items
    token_page = (
        filters.query(
            db.session.query(Tokens, Users)
            .join(Users, Users.id == Tokens.user_id)
            .filter(Users.type != "admin"),
            users=(Users.id,),
            teams=(Users.team_id,),
        )
        .order_by(Tokens.id.desc())
        .paginate(
            page=max(1, request.args.get("token_page", 1, type=int)),
            per_page=50,
            error_out=False,
        )
    )
    user_ids = {e.user_id for e in events if e.user_id}
    users = (
        {u.id: u for u in Users.query.filter(Users.id.in_(user_ids)).all()}
        if user_ids
        else {}
    )
    team_ids = {e.team_id for e in events if e.team_id} | {
        u.team_id for _, u in token_page.items if u.team_id
    }
    teams = (
        {t.id: t for t in Teams.query.filter(Teams.id.in_(team_ids)).all()}
        if team_ids
        else {}
    )
    summary = {}
    for e in events:
        key = ("t", e.team_id) if e.team_id else ("u", e.user_id)
        row = summary.setdefault(
            key,
            {
                "team": teams.get(e.team_id),
                "user": users.get(e.user_id),
                "ai": 0,
                "token": 0,
                "auto": 0,
                "labels": set(),
                "last": e.date,
            },
        )
        row["ai" if e.kind == "ai" else "token" if e.kind == "api-token" else "auto"] += 1
        row["labels"].add(e.label)
    for row in summary.values():
        row["labels"] = sorted(row["labels"])
    summary = sorted(summary.values(), key=lambda row: row["last"], reverse=True)
    now = datetime.utcnow()
    tokens = [
        {
            "id": t.id,
            "user": u,
            "team": teams.get(u.team_id),
            "created": t.created,
            "expiration": t.expiration,
            "description": t.description,
            "expired": bool(t.expiration and t.expiration < now),
        }
        for t, u in token_page.items
    ]
    return render_template(
        template("admin_activity.html"),
        enabled=settings.enabled("client_activity"),
        events=events,
        users=users,
        teams=teams,
        total=pagination.total,
        summary=summary,
        message=message,
        tokens=tokens,
        pagination=pagination,
        token_page=token_page,
        kind=kind,
        filters=filters,
    )


@blueprint.route("/admin/warden/devices", methods=["GET", "POST"])
@admins_only
def devices():
    message = handle_removal(DeviceSession, DeviceSession.device_id)
    filters = Filters(("player", "team", "ip"))
    shared = (
        db.session.query(DeviceSession.device_id)
        .group_by(DeviceSession.device_id)
        .having(sa.func.count(DeviceSession.user_id) > 1)
        .all()
    )
    ids = [d for (d,) in shared]
    rows = (
        DeviceSession.query.filter(DeviceSession.device_id.in_(ids))
        .order_by(DeviceSession.last_seen.desc())
        .all()
        if ids
        else []
    )
    user_ids = {r.user_id for r in rows}
    users = (
        {u.id: u for u in Users.query.filter(Users.id.in_(user_ids)).all()}
        if user_ids
        else {}
    )
    by_device = {}
    for r in rows:
        u = users.get(r.user_id)
        if u is None:
            continue
        d = by_device.setdefault(
            r.device_id,
            {
                "device_id": r.device_id,
                "rows": [],
                "teams": set(),
                "last_seen": r.last_seen,
                "ip": r.ip,
                "user_agent": r.user_agent,
                "ips": set(),
            },
        )
        d["rows"].append({"user": u, "last_seen": r.last_seen})
        d["ips"].add(r.ip)
        d["teams"].add(u.team_id if teams_mode() else u.id)
        if r.last_seen > d["last_seen"]:
            d["last_seen"], d["ip"], d["user_agent"] = r.last_seen, r.ip, r.user_agent
    newest_first = [
        d
        for d in sorted(by_device.values(), key=lambda d: d["last_seen"], reverse=True)
        if filters.keep(
            [row["user"].id for row in d["rows"]],
            [row["user"].team_id for row in d["rows"]],
            ips=d["ips"],
        )
    ]
    cross = [d for d in newest_first if len(d["teams"]) > 1]
    same = [d for d in newest_first if len(d["teams"]) == 1]
    for d in same:
        d["team"] = d["rows"][0]["user"].team
    return render_template(
        template("admin_devices.html"),
        enabled=settings.enabled("device_tracking"),
        teams_mode=teams_mode(),
        cross_team=cross,
        same_team=same,
        devices_total=db.session.query(
            sa.func.count(sa.distinct(DeviceSession.device_id))
        ).scalar(),
        accounts_total=DeviceSession.query.count(),
        message=message,
        filters=filters,
    )


@blueprint.route("/admin/warden/sharing", methods=["GET", "POST"])
@admins_only
def flag_sharing():
    message = None
    if request.method == "POST":
        action = request.form.get("action")
        if action == "watch":
            ids = {int(c) for c in request.form.getlist("challenge_id") if c.isdigit()}
            known = {c for (c,) in db.session.query(Challenges.id).filter(Challenges.id.in_(ids))}
            sharing.save_watched(known)
            message = f"Watching {len(known)} challenge(s) for shared flags."
        elif action == "scan":
            message = f"Scan finished: {sharing.scan()} new shared flag(s) found."
        else:
            message = handle_removal(FlagShare)

    flag_types = {}
    for challenge_id, flag_type in db.session.query(Flags.challenge_id, Flags.type).distinct():
        flag_types.setdefault(challenge_id, set()).add(flag_type)
    watched = sharing.watched()
    challenges = [
        {
            "id": c.id,
            "name": c.name,
            "category": c.category,
            "type": c.type,
            "flag_types": sorted(flag_types.get(c.id, ())),
            "watched": c.id in watched,
        }
        for c in Challenges.query.order_by(Challenges.category, Challenges.name).all()
    ]
    names = {c["id"]: c["name"] for c in challenges}

    filters = Filters()
    query = filters.query(
        FlagShare.query,
        users=(FlagShare.user_id, FlagShare.owner_user_id),
        teams=(FlagShare.team_id, FlagShare.owner_team_id),
        challenges=(FlagShare.challenge_id,),
        ips=(FlagShare.ip,),
    )
    pagination = query.order_by(FlagShare.date.desc()).paginate(
        page=max(1, request.args.get("page", 1, type=int)), per_page=100, error_out=False
    )
    events = pagination.items
    user_ids = {i for e in events for i in (e.user_id, e.owner_user_id) if i}
    team_ids = {i for e in events for i in (e.team_id, e.owner_team_id) if i}
    users = {u.id: u for u in Users.query.filter(Users.id.in_(user_ids)).all()} if user_ids else {}
    teams = {t.id: t for t in Teams.query.filter(Teams.id.in_(team_ids)).all()} if team_ids else {}
    return render_template(
        template("admin_sharing.html"),
        enabled=settings.enabled("flag_sharing"),
        message=message,
        challenges=challenges,
        names=names,
        events=events,
        users=users,
        teams=teams,
        total=pagination.total,
        pagination=pagination,
        teams_mode=teams_mode(),
        filters=filters,
    )


def _duration(seconds):
    if seconds is None:
        return ""
    hours, rest = divmod(int(seconds), 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours} h {minutes} min"
    if minutes:
        return f"{minutes} min {secs} s"
    return f"{secs} s"


@blueprint.route("/admin/warden/fast-solves", methods=["GET", "POST"])
@admins_only
def fast_solves():
    message = None
    if request.method == "POST" and request.form.get("action") == "fast-settings":
        count, seconds = _int(request.form.get("count")), _int(request.form.get("seconds"))
        count_low, count_high = fastsolves.LIMITS["count"]
        sec_low, sec_high = fastsolves.LIMITS["seconds"]
        if count is None or seconds is None or not (
            count_low <= count <= count_high and sec_low <= seconds <= sec_high
        ):
            message = (
                f"Not saved: use {count_low} to {count_high} solves "
                f"and {sec_low} to {sec_high} seconds."
            )
        else:
            ids = {int(c) for c in request.form.getlist("ignore") if c.isdigit()}
            known = {c for (c,) in db.session.query(Challenges.id).filter(Challenges.id.in_(ids))}
            fastsolves.save_settings(count, seconds)
            fastsolves.save_ignored(known)
            message = "Fast solve settings saved."

    filters = Filters()
    found = [
        b
        for b in fastsolves.bursts()
        if filters.keep(
            [b["user_id"]],
            [b["team_id"]],
            [s.challenge_id for s in b["solves"]],
            ips=b["ips"],
        )
    ]
    per_page = 100
    pages = max(1, -(-len(found) // per_page))
    page = min(pages, max(1, request.args.get("page", 1, type=int)))
    shown = found[(page - 1) * per_page : page * per_page]

    ignored = fastsolves.ignored()
    challenges = Challenges.query.order_by(Challenges.category, Challenges.name).all()
    names = {c.id: c.name for c in challenges}
    user_ids = {b["user_id"] for b in shown}
    team_ids = {b["team_id"] for b in shown if b["team_id"]}
    users = {u.id: u for u in Users.query.filter(Users.id.in_(user_ids)).all()} if user_ids else {}
    teams = {t.id: t for t in Teams.query.filter(Teams.id.in_(team_ids)).all()} if team_ids else {}
    return render_template(
        template("admin_fast.html"),
        message=message,
        limits=fastsolves.settings(),
        challenges=[
            {"id": c.id, "name": c.name, "category": c.category, "ignored": c.id in ignored}
            for c in challenges
        ],
        names=names,
        bursts=shown,
        total=len(found),
        page=page,
        pages=pages,
        users=users,
        teams=teams,
        teams_mode=teams_mode(),
        duration=_duration,
        filters=filters,
    )


@blueprint.route("/admin/warden/honeypots", methods=["GET", "POST"])
@admins_only
def honeypot_flags():
    message = None
    if request.method == "POST":
        action = request.form.get("action")
        if action == "add-honeypot":
            challenge_id = _int(request.form.get("challenge_id"))
            if challenge_id is not None and not Challenges.query.filter_by(id=challenge_id).first():
                challenge_id = None
            added = honeypots.add(
                request.form.get("flag"), challenge_id, request.form.get("note")
            )
            message = "Honeypot flag added." if added else "Not added: empty or already listed."
        elif action == "remove-honeypot":
            honeypots.remove(_int(request.form.get("id")))
            message = "Honeypot flag removed."
        else:
            message = handle_removal(HoneypotHit)

    filters = Filters()
    query = filters.query(
        HoneypotHit.query,
        users=(HoneypotHit.user_id,),
        teams=(HoneypotHit.team_id,),
        challenges=(HoneypotHit.challenge_id,),
        ips=(HoneypotHit.ip,),
    )
    pagination = query.order_by(HoneypotHit.date.desc()).paginate(
        page=max(1, request.args.get("page", 1, type=int)), per_page=100, error_out=False
    )
    hits = pagination.items
    items = honeypots.load()
    notes = {}
    for item in items:
        notes.setdefault(item["flag"], item["note"])
    challenges = Challenges.query.order_by(Challenges.category, Challenges.name).all()
    return render_template(
        template("admin_honeypots.html"),
        enabled=settings.enabled("honeypot_flags"),
        message=message,
        honeypots=items,
        notes=notes,
        challenges=challenges,
        names={c.id: c.name for c in challenges},
        hits=hits,
        users=_lookup(Users, {h.user_id for h in hits}),
        teams=_lookup(Teams, {h.team_id for h in hits}),
        total=pagination.total,
        pagination=pagination,
        teams_mode=teams_mode(),
        filters=filters,
    )


@blueprint.route("/admin/warden/accounts")
@admins_only
def accounts_list():
    filters = Filters(("player", "team", "ip"))
    counts = accounts.summary()
    ids = accounts.matching(filters) if filters.active else set(counts)
    model = accounts.model()
    names = dict(db.session.query(model.id, model.name).filter(model.id.in_(ids))) if ids else {}
    rows = []
    for account_id, name in names.items():
        found = counts.get(account_id, {})
        rows.append({"id": account_id, "name": name, "counts": found, "total": sum(found.values())})
    rows.sort(key=lambda r: (-r["total"], r["name"].lower()))
    per_page = 100
    pages = max(1, -(-len(rows) // per_page))
    page = min(pages, max(1, request.args.get("page", 1, type=int)))
    shown = rows[(page - 1) * per_page : page * per_page]
    found = _lookup(model, [row["id"] for row in shown])
    for row in shown:
        row["account"] = found[row["id"]]
    return render_template(
        template("admin_accounts.html"),
        rows=shown,
        total=len(rows),
        page=page,
        pages=pages,
        columns=accounts.COLUMNS,
        teams_mode=teams_mode(),
        filters=filters,
    )


@blueprint.route("/admin/warden/accounts/<int:account_id>", methods=["GET", "POST"])
@admins_only
def account(account_id):
    target = accounts.model().query.filter_by(id=account_id).first_or_404()
    key = f"{'t' if teams_mode() else 'u'}{account_id}"
    message = None
    if request.method == "POST":
        action = request.form.get("action")
        challenge_id = _int(request.form.get("challenge_id"))
        if action == "add-block" and Challenges.query.filter_by(id=challenge_id).first():
            blocks.add_block(challenge_id, key)
            message = "Challenge blocked."
        elif action == "remove-block" and challenge_id:
            blocks.remove_block(challenge_id, key)
            message = "Block removed."
    data = accounts.detail(account_id)

    user_ids = {m.id for m in data["members"]}
    user_ids |= {e.user_id for e in data["events"] + data["lockouts"] + data["honeypots"]}
    user_ids |= {i for e in data["copied"] + data["sources"] for i in (e.user_id, e.owner_user_id)}
    user_ids |= {b["user_id"] for b in data["bursts"]}
    user_ids |= {u for d in data["devices"] for u in d["users"]}
    account_ids = {i for d in data["devices"] for i in d["others"]}
    account_ids |= {i for r in data["ips"] for i in r["others"]}
    for e in data["copied"] + data["sources"]:
        if teams_mode():
            account_ids |= {e.team_id, e.owner_team_id}
        else:
            account_ids |= {e.user_id, e.owner_user_id}
    return render_template(
        template("admin_account.html"),
        target=target,
        message=message,
        data=data,
        users=_lookup(Users, user_ids),
        others=_lookup(accounts.model(), account_ids),
        names=dict(db.session.query(Challenges.id, Challenges.name).all()),
        teams_mode=teams_mode(),
        duration=_duration,
    )
