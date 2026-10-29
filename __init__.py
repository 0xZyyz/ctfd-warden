"""Warden: anti-cheat and fair-play toolkit for CTFd.

Clone or copy this repository into ``CTFd/plugins/`` and restart CTFd. Everything is managed
from Admin -> Warden; see README.md for each feature.
"""

import logging

from flask import request

from CTFd.models import db
from CTFd.plugins import (
    register_admin_plugin_menu_bar,
    register_plugin_assets_directory,
    register_plugin_script,
)
from CTFd.plugins.migrations import upgrade
from CTFd.utils.user import authed, get_current_user, is_admin

from . import activity, admin, blocks, brackets, devices, lockout, privacy, settings  # noqa: F401
from .common import ASSETS, PLUGIN_NAME, blueprint, request_path, template

log = logging.getLogger("warden")


def _before_request():
    on = settings.enabled
    path = request_path()
    if on("team_privacy"):
        privacy.before_request(path)
    if on("regional_brackets"):
        brackets.before_request(path)
    if not authed() or is_admin():
        return None
    user = get_current_user()
    if user is None:
        return None

    blocked = blocks.before_request(path, user)
    if blocked is not None:
        return blocked
    if on("client_activity"):
        activity.before_request(path, user)
    if on("device_tracking"):
        devices.before_request(user)
    if on("flag_lockout"):
        locked = lockout.before_request(path, user)
        if locked is not None:
            return locked
    return None


def _after_request(response):
    on = settings.enabled
    path = request_path()
    # Privacy filtering is not wrapped below: if it fails, the response must fail rather than leak.
    if on("team_privacy"):
        privacy.after_request(path, response)
    try:
        if authed() and not is_admin():
            user = get_current_user()
            if user is not None:
                blocks.after_request(path, user, response)
        if on("client_activity"):
            activity.after_request(response)
        if on("flag_lockout"):
            lockout.after_request(response)
        if on("device_tracking"):
            devices.after_request(response)
        if on("regional_brackets"):
            brackets.after_request(path, response)
    except Exception:
        # Never turn a player's (already handled) request into an error page.
        log.exception("warden: after_request hook failed for %s", request.path)
        db.session.rollback()
    return response


def load(app):
    upgrade(plugin_name=PLUGIN_NAME)
    app.register_blueprint(blueprint)
    register_plugin_assets_directory(app, base_path=ASSETS)
    # Reports in-page browser-automation marks; works with any theme that renders Plugins.scripts.
    register_plugin_script(ASSETS + "warden.js")
    with app.app_context():
        if settings.enabled("regional_brackets"):
            brackets.ensure_brackets()
        lockout.warn_without_redis()
    app.before_request(_before_request)
    app.after_request(_after_request)
    # One navbar link; the Warden pages have their own tabs (Overview, Client activity, Shared devices).
    register_admin_plugin_menu_bar("Warden", "/admin/warden")
    app.jinja_env.globals["warden_nav"] = template("_nav.html")
