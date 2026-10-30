import json

from CTFd.models import Solves, Users
from CTFd.utils import get_config, set_config

COUNT_KEY = "warden_fast_solve_count"
SECONDS_KEY = "warden_fast_solve_seconds"
IGNORED_KEY = "warden_fast_solve_ignored"
DEFAULTS = {"count": 3, "seconds": 120}
LIMITS = {"count": (2, 50), "seconds": (10, 86400)}


def _clamp(name, value):
    low, high = LIMITS[name]
    return min(high, max(low, value))


def settings():
    out = {}
    for name, key in (("count", COUNT_KEY), ("seconds", SECONDS_KEY)):
        try:
            value = int(get_config(key) or DEFAULTS[name])
        except (TypeError, ValueError):
            value = DEFAULTS[name]
        out[name] = _clamp(name, value)
    return out


def save_settings(count, seconds):
    set_config(COUNT_KEY, str(int(count)))
    set_config(SECONDS_KEY, str(int(seconds)))


def ignored():
    try:
        data = json.loads(get_config(IGNORED_KEY) or "[]")
    except (TypeError, ValueError):
        return set()
    return {int(c) for c in data if str(c).isdigit()} if isinstance(data, list) else set()


def save_ignored(challenge_ids):
    set_config(IGNORED_KEY, json.dumps(sorted({int(c) for c in challenge_ids})))


def _bursts(solves, count, seconds):
    marked = [False] * len(solves)
    for i in range(len(solves) - count + 1):
        if (solves[i + count - 1].date - solves[i].date).total_seconds() <= seconds:
            for j in range(i, i + count):
                marked[j] = True
    runs, current = [], []
    for solve, hit in zip(solves, marked):
        if hit:
            current.append(solve)
        elif current:
            runs.append(current)
            current = []
    if current:
        runs.append(current)
    return runs


def bursts():
    limits, skip = settings(), ignored()
    by_user = {}
    solves = (
        Solves.query.join(Users, Users.id == Solves.user_id)
        .filter(Users.type != "admin")
        .order_by(Solves.date.asc(), Solves.id.asc())
    )
    for solve in solves:
        if solve.challenge_id not in skip:
            by_user.setdefault(solve.user_id, []).append(solve)
    found = []
    for user_id, user_solves in by_user.items():
        for run in _bursts(user_solves, limits["count"], limits["seconds"]):
            found.append(
                {
                    "user_id": user_id,
                    "team_id": run[-1].team_id,
                    "start": run[0].date,
                    "end": run[-1].date,
                    "seconds": int((run[-1].date - run[0].date).total_seconds()),
                    "solves": run,
                    "ips": sorted({s.ip for s in run if s.ip}),
                }
            )
    found.sort(key=lambda b: b["end"], reverse=True)
    return found
