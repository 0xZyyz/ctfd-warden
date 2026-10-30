from datetime import datetime

import sqlalchemy as sa
from flask import render_template, request

from CTFd.models import Brackets, Challenges, Flags, Teams, Tokens, Users, db
from CTFd.utils.decorators import admins_only

from . import blocks, brackets, settings, sharing
from .common import blueprint, handle_removal, teams_mode, template
from .models import ClientEvent, DeviceSession, FlagShare, LockoutEvent


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
    if kind == "t":
        team = Teams.query.filter_by(id=account_id).first()
        name = team.name if team else f"Deleted team #{account_id}"
        return name, "admin.teams_detail", {"team_id": account_id}
    user = Users.query.filter_by(id=account_id).first()
    name = user.name if user else f"Deleted user #{account_id}"
    return name, "admin.users_detail", {"user_id": account_id}


def _handle_post():
    action = request.form.get("action")
    if action == "features":
        for name in settings.FEATURES:
            if settings.env_override(name) is None:
                settings.set_enabled(name, request.form.get(name) == "on")
        if settings.enabled("regional_brackets"):
            brackets.ensure_brackets()
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
    if action == "region-settings":
        name = (request.form.get("name") or "").strip()[:64]
        outside = (request.form.get("outside_name") or "").strip()[:64]
        codes = settings.parse_countries(request.form.get("countries"))
        if not name or not outside or name == outside or not codes:
            return "Region not saved: give two different bracket names and at least one country code."
        old = settings.region_settings()
        settings.save_region_settings(name, outside, " ".join(codes))
        brackets.ensure_brackets(old_names=(old["name"], old["outside_name"]))
        return "Region saved and accounts placed again."
    if action == "reset-brackets":
        brackets.save_overrides({})
        brackets.classify_all()
        return "Every account is back to automatic placement."
    if action == "reset-bracket":
        pinned = brackets.overrides()
        pinned.pop(request.form.get("account", ""), None)
        brackets.save_overrides(pinned)
        brackets.classify_all()
        return "That account is back to automatic placement."
    return None


@blueprint.route("/admin/warden", methods=["GET", "POST"])
@admins_only
def overview():
    message = _handle_post() if request.method == "POST" else None

    lockouts = LockoutEvent.query.order_by(LockoutEvent.date.desc()).limit(200).all()
    for e in lockouts:
        e.team = Teams.query.get(e.team_id) if e.team_id else None
        e.user = Users.query.get(e.user_id) if e.user_id else None
        e.challenge = Challenges.query.get(e.challenge_id) if e.challenge_id else None

    challenge_names = dict(db.session.query(Challenges.id, Challenges.name).all())
    block_rows = []
    for challenge_id, accounts in sorted(blocks.load_blocks().items()):
        for account in sorted(accounts):
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

    pinned_rows = []
    if settings.enabled("regional_brackets"):
        names = {b.id: b.name for b in Brackets.query.all()}
        for account, bracket_id in brackets.overrides().items():
            name, endpoint, args = _account_label(account)
            pinned_rows.append(
                {
                    "account": account,
                    "name": name,
                    "endpoint": endpoint,
                    "args": args,
                    "bracket": names.get(bracket_id, "No bracket"),
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
        region=settings.region_settings(),
        pinned=pinned_rows,
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

    query = ClientEvent.query
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
        db.session.query(Tokens, Users)
        .join(Users, Users.id == Tokens.user_id)
        .filter(Users.type != "admin")
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
    )


@blueprint.route("/admin/warden/devices", methods=["GET", "POST"])
@admins_only
def devices():
    message = handle_removal(DeviceSession, DeviceSession.device_id)
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
            },
        )
        d["rows"].append({"user": u, "last_seen": r.last_seen})
        d["teams"].add(u.team_id if teams_mode() else u.id)
        if r.last_seen > d["last_seen"]:
            d["last_seen"], d["ip"], d["user_agent"] = r.last_seen, r.ip, r.user_agent
    newest_first = sorted(by_device.values(), key=lambda d: d["last_seen"], reverse=True)
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

    pagination = FlagShare.query.order_by(FlagShare.date.desc()).paginate(
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
    )
