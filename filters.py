import sqlalchemy as sa
from flask import request

from CTFd.models import Challenges, Teams, Users, db

from .common import teams_mode

LABELS = {
    "player": "Player name",
    "team": "Team name",
    "challenge": "Challenge name",
    "ip": "IP address",
}
MODELS = {"player": Users, "team": Teams, "challenge": Challenges}


def like(column, text):
    return sa.func.lower(column).contains(text.lower(), autoescape=True)


class Filters:
    def __init__(self, fields=tuple(LABELS)):
        self.fields = [f for f in fields if f != "team" or teams_mode()]
        self.values = {f: (request.args.get(f) or "").strip()[:64] for f in self.fields}
        self.labels = LABELS
        self._ids = {}

    def __getitem__(self, name):
        return self.values.get(name, "")

    @property
    def active(self):
        return any(self.values.values())

    def args(self):
        return {k: v for k, v in self.values.items() if v}

    def ids(self, name):
        if not self[name]:
            return None
        if name not in self._ids:
            model = MODELS[name]
            query = db.session.query(model.id).filter(like(model.name, self[name]))
            self._ids[name] = {i for (i,) in query}
        return self._ids[name]

    def keep(self, user_ids=(), team_ids=(), challenge_ids=(), ips=None):
        wanted_by_name = (("player", user_ids), ("team", team_ids), ("challenge", challenge_ids))
        for name, values in wanted_by_name:
            wanted = self.ids(name)
            if wanted is not None and not wanted & {v for v in values if v is not None}:
                return False
        needle = self["ip"]
        return not needle or ips is None or any(ip and needle in ip for ip in ips)

    def query(self, query, users=(), teams=(), challenges=(), ips=()):
        for name, columns in (("player", users), ("team", teams), ("challenge", challenges)):
            wanted = self.ids(name)
            if wanted is not None and columns:
                query = query.filter(sa.or_(*[c.in_(wanted) for c in columns]))
        if self["ip"] and ips:
            query = query.filter(sa.or_(*[like(c, self["ip"]) for c in ips]))
        return query
