import os

from flask import g, has_request_context

from CTFd.utils import get_config, set_config

TRUE = ("1", "true", "yes", "on")
FALSE = ("0", "false", "no", "off")

FEATURES = {
    "client_activity": (
        True,
        "Client activity",
        "Log requests from self-identified AI agents, automation libraries and CTFd API tokens.",
    ),
    "device_tracking": (
        True,
        "Shared devices",
        "Give every browser a random device cookie and list devices used by several accounts.",
    ),
    "flag_lockout": (
        True,
        "Flag brute-force lockout",
        "Lock an account out of a challenge after too many wrong flags in a short window.",
    ),
    "flag_sharing": (
        True,
        "Flag sharing",
        "On challenges you mark as having unique flags, report the same flag submitted by two teams.",
    ),
    "honeypot_flags": (
        True,
        "Honeypot flags",
        "Record every player who submits one of your decoy flags.",
    ),
    "team_privacy": (
        False,
        "Team privacy",
        "Hide team rosters, member countries and the user list from other players.",
    ),
}

LOCK_DEFAULTS = {"threshold": 60, "window": 300, "duration": 600}
LOCK_MINIMUMS = {"threshold": 5, "window": 60, "duration": 60}


def _key(name):
    return f"warden_{name}"


def _as_bool(value):
    value = str(value).strip().lower()
    if value in TRUE:
        return True
    if value in FALSE:
        return False
    return None


def env_override(feature):
    return _as_bool(os.environ.get(f"WARDEN_{feature.upper()}", ""))


def _lookup(feature):
    forced = env_override(feature)
    if forced is not None:
        return forced
    stored = _as_bool(get_config(_key(feature), default=""))
    return FEATURES[feature][0] if stored is None else stored


def enabled(feature):
    if not has_request_context():
        return _lookup(feature)
    cached = g.setdefault("warden_features", {})
    if feature not in cached:
        cached[feature] = _lookup(feature)
    return cached[feature]


def set_enabled(feature, value):
    set_config(_key(feature), "1" if value else "0")
    if has_request_context():
        g.pop("warden_features", None)


def lock_settings():
    out = {}
    for name, default in LOCK_DEFAULTS.items():
        try:
            value = int(get_config(_key(f"lock_{name}")) or default)
        except (TypeError, ValueError):
            value = default
        out[name] = max(LOCK_MINIMUMS[name], value)
    return out


def save_lock_settings(values):
    for name, value in values.items():
        set_config(_key(f"lock_{name}"), str(int(value)))

