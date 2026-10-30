import os

from flask import Blueprint, request

from CTFd.models import db
from CTFd.utils import get_config

blueprint = Blueprint("warden", __name__)

PLUGIN_NAME = os.path.basename(os.path.dirname(os.path.abspath(__file__)))
TEMPLATES = f"plugins/{PLUGIN_NAME}/templates"
ASSETS = f"/plugins/{PLUGIN_NAME}/assets/"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}


def template(name):
    return f"{TEMPLATES}/{name}"


def request_path():
    root = request.script_root.rstrip("/")
    path = request.path
    return path[len(root) :] if root and path.startswith(root) else path


def teams_mode():
    return get_config("user_mode") == "teams"


def account_key(user):
    if teams_mode():
        return f"t{user.team_id}" if user.team_id else None
    return f"u{user.id}"


def handle_removal(model, id_column=None):
    if request.method != "POST":
        return None
    action = request.form.get("action")
    if action == "clear":
        n = model.query.delete(synchronize_session=False)
        db.session.commit()
        return f"Removed all {n} entries."
    if action == "remove":
        column = id_column if id_column is not None else model.id
        n = model.query.filter(column == request.form.get("id", "")).delete(
            synchronize_session=False
        )
        db.session.commit()
        return "Entry removed." if n else "Nothing to remove."
    return None
