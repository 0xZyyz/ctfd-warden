from collections import Counter, defaultdict

import sqlalchemy as sa

from CTFd.models import Solves, Teams, Tokens, Users, db

from . import blocks, fastsolves
from .common import teams_mode
from .filters import like
from .models import ClientEvent, DeviceSession, FlagShare, LockoutEvent

COLUMNS = (
    ("shared_flags", "Copied flags"),
    ("flag_sources", "Flags copied from them"),
    ("devices", "Shared devices"),
    ("bursts", "Fast solves"),
    ("lockouts", "Lockouts"),
    ("ai", "AI clients"),
    ("automation", "Scripts"),
    ("api-token", "API tokens"),
    ("blocks", "Blocks"),
)


def model():
    return Teams if teams_mode() else Users


def _owners():
    return dict(db.session.query(Users.id, Users.team_id)) if teams_mode() else None


def _account_of(user_id, owners):
    return owners.get(user_id) if owners is not None else user_id


def _column(table, team_column, user_column):
    return getattr(table, team_column if teams_mode() else user_column)


def _bursts(account_id=None):
    key = "team_id" if teams_mode() else "user_id"
    found = fastsolves.bursts()
    return found if account_id is None else [b for b in found if b[key] == account_id]


def summary():
    owners = _owners()
    counts = defaultdict(Counter)
    column = _column(ClientEvent, "team_id", "user_id")
    for account, kind, n in db.session.query(column, ClientEvent.kind, sa.func.count()).group_by(
        column, ClientEvent.kind
    ):
        counts[account][kind] += n
    column = _column(LockoutEvent, "team_id", "user_id")
    for account, n in db.session.query(column, sa.func.count()).group_by(column):
        counts[account]["lockouts"] += n
    for name, team_column, user_column in (
        ("shared_flags", "team_id", "user_id"),
        ("flag_sources", "owner_team_id", "owner_user_id"),
    ):
        column = _column(FlagShare, team_column, user_column)
        for account, n in db.session.query(column, sa.func.count()).group_by(column):
            counts[account][name] += n
    by_device = defaultdict(set)
    for device, user_id in db.session.query(DeviceSession.device_id, DeviceSession.user_id):
        by_device[device].add(_account_of(user_id, owners))
    for accounts in by_device.values():
        accounts.discard(None)
        if len(accounts) > 1:
            for account in accounts:
                counts[account]["devices"] += 1
    key = "team_id" if teams_mode() else "user_id"
    for burst in _bursts():
        counts[burst[key]]["bursts"] += 1
    prefix = "t" if teams_mode() else "u"
    for keys in blocks.load_blocks().values():
        for account in keys:
            if account.startswith(prefix) and account[1:].isdigit():
                counts[int(account[1:])]["blocks"] += 1
    counts.pop(None, None)
    return counts


def members_of(account_id):
    if teams_mode():
        return Users.query.filter_by(team_id=account_id).order_by(Users.name).all()
    user = Users.query.filter_by(id=account_id).first()
    return [user] if user else []


def _devices(account_id, member_ids, owners):
    sessions = DeviceSession.query.filter(DeviceSession.user_id.in_(member_ids)).all()
    device_ids = {s.device_id for s in sessions}
    if not device_ids:
        return []
    rows = defaultdict(list)
    for s in DeviceSession.query.filter(DeviceSession.device_id.in_(device_ids)):
        rows[s.device_id].append(s)
    devices = []
    for device, seen in rows.items():
        others = {_account_of(s.user_id, owners) for s in seen} - {account_id, None}
        if not others and len(seen) < 2:
            continue
        last = max(seen, key=lambda s: s.last_seen)
        devices.append(
            {
                "device_id": device,
                "users": sorted(s.user_id for s in seen),
                "others": sorted(others),
                "last_seen": last.last_seen,
                "ip": last.ip,
                "user_agent": last.user_agent,
            }
        )
    devices.sort(key=lambda d: d["last_seen"], reverse=True)
    devices.sort(key=lambda d: not d["others"])
    return devices


def _ips(account_id, member_ids, owners):
    used = defaultdict(set)
    for user_id, ip in db.session.query(Solves.user_id, Solves.ip).filter(
        Solves.user_id.in_(member_ids)
    ):
        if ip:
            used[ip].add(user_id)
    for user_id, ip in db.session.query(DeviceSession.user_id, DeviceSession.ip).filter(
        DeviceSession.user_id.in_(member_ids)
    ):
        if ip:
            used[ip].add(user_id)
    if not used:
        return []
    others = defaultdict(set)
    for table in (Solves, DeviceSession):
        for user_id, ip in db.session.query(table.user_id, table.ip).filter(
            table.ip.in_(list(used))
        ):
            account = _account_of(user_id, owners)
            if account and account != account_id:
                others[ip].add(account)
    rows = [
        {"ip": ip, "users": sorted(users), "others": sorted(others.get(ip, ()))}
        for ip, users in used.items()
    ]
    rows.sort(key=lambda r: (-len(r["others"]), r["ip"]))
    return rows


def detail(account_id):
    owners = _owners()
    members = members_of(account_id)
    member_ids = [m.id for m in members]
    event_column = _column(ClientEvent, "team_id", "user_id")
    key = f"{'t' if teams_mode() else 'u'}{account_id}"
    return {
        "members": members,
        "clients": db.session.query(
            ClientEvent.kind, ClientEvent.label, sa.func.count(), sa.func.max(ClientEvent.date)
        )
        .filter(event_column == account_id)
        .group_by(ClientEvent.kind, ClientEvent.label)
        .order_by(sa.func.max(ClientEvent.date).desc())
        .all(),
        "events": ClientEvent.query.filter(event_column == account_id)
        .order_by(ClientEvent.id.desc())
        .limit(20)
        .all(),
        "lockouts": LockoutEvent.query.filter(
            _column(LockoutEvent, "team_id", "user_id") == account_id
        )
        .order_by(LockoutEvent.date.desc())
        .all(),
        "copied": FlagShare.query.filter(_column(FlagShare, "team_id", "user_id") == account_id)
        .order_by(FlagShare.date.desc())
        .all(),
        "sources": FlagShare.query.filter(
            _column(FlagShare, "owner_team_id", "owner_user_id") == account_id
        )
        .order_by(FlagShare.date.desc())
        .all(),
        "bursts": _bursts(account_id),
        "devices": _devices(account_id, member_ids, owners) if member_ids else [],
        "ips": _ips(account_id, member_ids, owners) if member_ids else [],
        "blocked": sorted(c for c, keys in blocks.load_blocks().items() if key in keys),
        "tokens": Tokens.query.filter(Tokens.user_id.in_(member_ids)).count() if member_ids else 0,
        "key": key,
    }


def matching(filters):
    owners = _owners()
    query = db.session.query(model().id)
    if not teams_mode():
        query = query.filter(Users.type != "admin")
    found = {i for (i,) in query}
    team_ids = filters.ids("team")
    if team_ids is not None:
        found &= team_ids
    user_ids = filters.ids("player")
    if user_ids is not None:
        found &= {_account_of(u, owners) for u in user_ids}
    if filters["ip"]:
        users = set()
        for table in (Solves, DeviceSession):
            users |= {
                u for (u,) in db.session.query(table.user_id).filter(like(table.ip, filters["ip"]))
            }
        found &= {_account_of(u, owners) for u in users}
    found.discard(None)
    return found
