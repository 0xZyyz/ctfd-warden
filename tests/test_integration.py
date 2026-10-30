from datetime import datetime, timedelta

import pytest

from CTFd.models import Brackets, Flags, Solves, Teams, Users, db
from CTFd.plugins.warden import blocks, brackets, fastsolves, settings, sharing
from CTFd.plugins.warden.models import (
    ChallengeView,
    ClientEvent,
    DeviceSession,
    FlagShare,
    LockoutEvent,
)
from CTFd.utils.security.auth import generate_user_token
from tests.helpers import (
    create_ctfd,
    destroy_ctfd,
    gen_challenge,
    gen_fail,
    gen_flag,
    gen_solve,
    gen_team,
    gen_user,
    login_as_user,
)

BROWSER = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/130.0 Safari/537.36",
    "Accept-Language": "en",
}


@pytest.fixture
def app():
    application = create_ctfd(enable_plugins=True)
    yield application
    destroy_ctfd(application)


@pytest.fixture
def teams_app():
    application = create_ctfd(enable_plugins=True, user_mode="teams")
    yield application
    destroy_ctfd(application)


def player(app, name="player", **kwargs):
    with app.app_context():
        user = gen_user(db, name=name, email=f"{name}@example.test", verified=True, **kwargs)
        return user.id


def nonce(client):
    with client.session_transaction() as sess:
        return sess["nonce"]


def challenge_ids(client):
    return [c["id"] for c in client.get("/api/v1/challenges", headers=BROWSER).get_json()["data"]]


def test_players_reach_challenges_without_extra_steps(app):
    with app.test_client() as client:
        client.get("/register")
        response = client.post(
            "/register",
            data={
                "name": "newplayer",
                "email": "new@example.test",
                "password": "password",
                "nonce": nonce(client),
            },
        )
        assert response.status_code == 302
        assert "rules-acceptance" not in response.location
        assert client.get("/api/v1/challenges", headers=BROWSER).status_code == 200


def test_env_override_wins_over_admin_switch(app, monkeypatch):
    monkeypatch.setenv("WARDEN_FLAG_LOCKOUT", "0")
    with app.app_context():
        settings.set_enabled("flag_lockout", True)
        assert settings.enabled("flag_lockout") is False
        assert settings.env_override("flag_lockout") is False


def test_flag_lockout_after_threshold(app):
    user_id = player(app)
    with app.app_context():
        challenge_id = gen_challenge(db).id
        gen_flag(db, challenge_id=challenge_id, content="flag{right}")
        settings.save_lock_settings({"threshold": 5, "window": 300, "duration": 600})
    with login_as_user(app, name="player") as client:
        for _ in range(5):
            r = client.post(
                "/api/v1/challenges/attempt",
                json={"challenge_id": challenge_id, "submission": "flag{wrong}"},
                headers=BROWSER,
            )
            assert r.get_json()["data"]["status"] == "incorrect"
        r = client.post(
            "/api/v1/challenges/attempt",
            json={"challenge_id": challenge_id, "submission": "flag{right}"},
            headers=BROWSER,
        )
        assert r.status_code == 429
        assert r.get_json()["data"]["status"] == "ratelimited"
    with app.app_context():
        event = LockoutEvent.query.one()
        assert event.user_id == user_id and event.challenge_id == challenge_id
        assert event.attempts == 5


def test_challenge_block_hides_and_refuses_the_challenge(app):
    user_id = player(app)
    player(app, name="other")
    with app.app_context():
        blocked = gen_challenge(db, name="blocked").id
        gen_flag(db, challenge_id=blocked, content="flag{x}")
        visible = gen_challenge(db, name="visible").id
        blocks.add_block(blocked, f"u{user_id}")
    with login_as_user(app, name="player") as client:
        assert challenge_ids(client) == [visible]
        assert client.get(f"/api/v1/challenges/{blocked}", headers=BROWSER).status_code == 404
        r = client.post(
            "/api/v1/challenges/attempt",
            json={"challenge_id": blocked, "submission": "flag{x}"},
            headers=BROWSER,
        )
        assert r.status_code == 403 and r.get_json()["data"]["status"] == "disabled"
    with login_as_user(app, name="other") as client:
        assert sorted(challenge_ids(client)) == sorted([blocked, visible])
    with app.app_context():
        blocks.remove_block(blocked, f"u{user_id}")
        assert blocks.load_blocks() == {}


def test_client_activity_is_sampled_per_client(app):
    player(app)
    with login_as_user(app, name="player") as client:
        client.get("/api/v1/challenges", headers=BROWSER)
        for _ in range(3):
            client.get("/api/v1/challenges", headers={"User-Agent": "python-requests/2.32"})
        client.get("/api/v1/challenges", headers={"User-Agent": "Mozilla/5.0 ChatGPT-User/1.0"})
    with app.app_context():
        events = sorted((e.kind, e.label) for e in ClientEvent.query.all())
        assert events == [("ai", "ChatGPT agent"), ("automation", "python-requests")]


def test_api_token_requests_and_browser_automation_signals(app):
    user_id = player(app)
    with app.app_context():
        expiration = datetime.utcnow() + timedelta(days=1)
        token = generate_user_token(Users.query.get(user_id), expiration=expiration).value
    with app.test_client() as client:
        r = client.get(
            "/api/v1/challenges",
            headers={"Authorization": f"Token {token}", "Content-Type": "application/json", **BROWSER},
        )
        assert r.status_code == 200
    with login_as_user(app, name="player") as client:
        r = client.post(
            "/warden/client-signal",
            json={"signals": ["navigator.webdriver"], "page": "/challenges?x=1"},
            headers=BROWSER,
        )
        assert r.status_code == 200
    with app.app_context():
        kinds = {e.kind: e for e in ClientEvent.query.all()}
        assert set(kinds) == {"api-token", "automation"}
        assert kinds["automation"].label == "browser automation: navigator.webdriver"
        assert kinds["automation"].path == "/challenges"


def test_client_activity_switched_off_logs_nothing(app):
    player(app)
    with app.app_context():
        settings.set_enabled("client_activity", False)
    with login_as_user(app, name="player") as client:
        client.get("/api/v1/challenges", headers={"User-Agent": "curl/8.0"})
    with app.app_context():
        assert ClientEvent.query.count() == 0


def test_device_cookie_links_accounts_on_one_browser(app):
    player(app, name="alice")
    player(app, name="bob")
    with app.test_client() as client:
        client.get("/", headers=BROWSER)
        device = next(c.value for c in client.cookie_jar if c.name == "warden_device")
        assert len(device) == 32
        for name in ("alice", "bob"):
            client.get("/login")
            client.post("/login", data={"name": name, "password": "password", "nonce": nonce(client)})
            client.get("/scoreboard", headers=BROWSER)
            client.get("/logout")
    with app.app_context():
        rows = DeviceSession.query.all()
        assert {r.device_id for r in rows} == {device}
        assert len(rows) == 2
    with login_as_user(app, name="admin") as client:
        page = client.get("/admin/warden/devices")
        assert page.status_code == 200
        assert b"alice" in page.data and b"bob" in page.data


def test_regional_brackets_follow_member_nationalities(teams_app):
    app = teams_app
    with app.app_context():
        settings.set_enabled("regional_brackets", True)
        local = gen_team(db, name="Local", email="local@example.test", member_count=0)
        mixed = gen_team(db, name="Mixed", email="mixed@example.test", member_count=0)
        gen_user(db, name="a", email="a@example.test", team_id=local.id, country="TN")
        gen_user(db, name="b", email="b@example.test", team_id=local.id, country="EG")
        gen_user(db, name="c", email="c@example.test", team_id=mixed.id, country="TN")
        gen_user(db, name="d", email="d@example.test", team_id=mixed.id, country="FR")
        brackets.ensure_brackets()
        inside, outside, _ = brackets.brackets()
        assert Teams.query.filter_by(name="Local").one().bracket_id == inside.id
        assert Teams.query.filter_by(name="Mixed").one().bracket_id == outside.id

        settings.save_region_settings("Africa", "Rest of world", "TN EG")
        brackets.ensure_brackets(old_names=("MENA", "Outside MENA"))
        names = {b.name for b in Brackets.query.filter_by(type="teams")}
        assert names == {"Africa", "Rest of world"}
        assert Teams.query.filter_by(name="Local").one().bracket.name == "Africa"
        mixed_id = Teams.query.filter_by(name="Mixed").one().id
        africa = Brackets.query.filter_by(name="Africa").one().id

    with login_as_user(app, name="admin") as client:
        r = client.patch(f"/api/v1/teams/{mixed_id}", json={"bracket_id": africa})
        assert r.status_code == 200
    with app.app_context():
        assert brackets.overrides() == {f"t{mixed_id}": africa}
        brackets.classify_all()
        assert Teams.query.get(mixed_id).bracket_id == africa


def test_team_privacy_hides_rosters_and_user_list(teams_app):
    app = teams_app
    with app.app_context():
        settings.set_enabled("team_privacy", True)
        mine = gen_team(db, name="Mine", email="mine@example.test", member_count=0)
        theirs = gen_team(db, name="Theirs", email="theirs@example.test", member_count=0)
        gen_user(db, name="me", email="me@example.test", team_id=mine.id, verified=True)
        gen_user(db, name="them", email="them@example.test", team_id=theirs.id, country="FR")
        mine_id, theirs_id = mine.id, theirs.id
    with login_as_user(app, name="me") as client:
        assert client.get("/users", headers=BROWSER).status_code == 404
        assert client.get("/api/v1/users", headers=BROWSER).status_code == 404
        assert client.get("/api/v1/teams?country=FR", headers=BROWSER).status_code == 403
        other = client.get(f"/api/v1/teams/{theirs_id}", headers=BROWSER)
        assert other.headers["Cache-Control"] == "private, no-store"
        assert "members" not in other.get_json()["data"]
        own = client.get(f"/api/v1/teams/{mine_id}", headers=BROWSER).get_json()["data"]
        assert "members" in own
    with login_as_user(app, name="admin") as client:
        assert "members" in client.get(f"/api/v1/teams/{theirs_id}").get_json()["data"]


UNIQUE = r"flag\{unique_[0-9a-f]{16}\}"


def submit(client, challenge_id, flag):
    r = client.post(
        "/api/v1/challenges/attempt",
        json={"challenge_id": challenge_id, "submission": flag},
        headers=BROWSER,
    )
    return r.get_json()["data"]["status"]


def test_flag_sharing_catches_a_unique_flag_from_another_account(app):
    alice, bob = player(app, name="alice"), player(app, name="bob")
    with app.app_context():
        unique = gen_challenge(db, name="instanced").id
        gen_flag(db, challenge_id=unique, content=UNIQUE, type="regex")
        static = gen_challenge(db, name="static").id
        gen_flag(db, challenge_id=static, content="flag{same-for-all}")
        sharing.save_watched([unique])
    alices = "flag{unique_00112233aabbccdd}"
    with login_as_user(app, name="alice") as client:
        assert submit(client, unique, alices) == "correct"
        assert submit(client, static, "flag{same-for-all}") == "correct"
    with login_as_user(app, name="bob") as client:
        assert submit(client, static, "flag{same-for-all}") == "correct"
        assert submit(client, unique, "flag{unique_ffffffffffffffff}") == "correct"
    with app.app_context():
        assert FlagShare.query.count() == 0, "own unique flags and unwatched static flags are fine"
    carol = player(app, name="carol")
    with login_as_user(app, name="carol") as client:
        assert submit(client, unique, alices) == "correct"
        assert submit(client, unique, alices) == "already_solved"
    with app.app_context():
        event = FlagShare.query.one()
        assert (event.owner_user_id, event.user_id) == (alice, carol)
        assert event.flag == alices and event.status == "correct" and event.challenge_id == unique
        assert bob not in (event.owner_user_id, event.user_id)


def test_flag_sharing_catches_rejected_submissions_too(app):
    player(app, name="alice")
    bob = player(app, name="bob")
    with app.app_context():
        chal = gen_challenge(db).id
        gen_flag(db, challenge_id=chal, content="flag{alice-instance}")
        sharing.save_watched([chal])
    with login_as_user(app, name="alice") as client:
        assert submit(client, chal, "flag{alice-instance}") == "correct"
    with app.app_context():
        Flags.query.filter_by(challenge_id=chal).delete()
        db.session.commit()
        gen_flag(db, challenge_id=chal, content="flag{bob-instance}")
    with login_as_user(app, name="bob") as client:
        assert submit(client, chal, "flag{alice-instance}") == "incorrect"
    with app.app_context():
        event = FlagShare.query.one()
        assert event.user_id == bob and event.status == "incorrect"


def test_flag_sharing_ignores_teammates_and_flags_other_teams(teams_app):
    app = teams_app
    with app.app_context():
        red = gen_team(db, name="Red", email="red@example.test", member_count=0)
        blue = gen_team(db, name="Blue", email="blue@example.test", member_count=0)
        for name, team in (("r1", red), ("r2", red), ("b1", blue)):
            gen_user(db, name=name, email=f"{name}@example.test", team_id=team.id, verified=True)
        red_id, blue_id = red.id, blue.id
        chal = gen_challenge(db).id
        gen_flag(db, challenge_id=chal, content=UNIQUE, type="regex")
        sharing.save_watched([chal])
    flag = "flag{unique_0123456789abcdef}"
    with login_as_user(app, name="r1") as client:
        assert submit(client, chal, flag) == "correct"
    with login_as_user(app, name="r2") as client:
        submit(client, chal, flag)
    with app.app_context():
        assert FlagShare.query.count() == 0
    with login_as_user(app, name="b1") as client:
        assert submit(client, chal, flag) == "correct"
    with app.app_context():
        event = FlagShare.query.one()
        assert (event.owner_team_id, event.team_id) == (red_id, blue_id)


def test_flag_sharing_scan_of_past_submissions(app):
    alice, bob, carol = (player(app, name=n) for n in ("alice", "bob", "carol"))
    with app.app_context():
        chal = gen_challenge(db).id
        other = gen_challenge(db, name="unwatched").id
        gen_solve(db, user_id=alice, challenge_id=chal, provided="flag{unique_aaaa}")
        gen_solve(db, user_id=bob, challenge_id=chal, provided="flag{unique_aaaa}")
        gen_fail(db, user_id=carol, challenge_id=chal, provided="flag{unique_aaaa}")
        gen_solve(db, user_id=carol, challenge_id=chal, provided="flag{unique_cccc}")
        gen_solve(db, user_id=alice, challenge_id=other, provided="flag{x}")
        gen_solve(db, user_id=bob, challenge_id=other, provided="flag{x}")
        sharing.save_watched([chal])
        assert sharing.scan() == 2
        pairs = sorted((e.owner_user_id, e.user_id, e.status) for e in FlagShare.query.all())
        assert pairs == sorted([(alice, bob, "correct"), (alice, carol, "incorrect")])
        assert sharing.scan() == 0, "a second scan finds nothing new"


def test_flag_sharing_admin_page(app):
    with app.app_context():
        chal = gen_challenge(db, name="instanced").id
        gen_flag(db, challenge_id=chal, content=UNIQUE, type="regex")
    with login_as_user(app, name="admin") as client:
        page = client.get("/admin/warden/sharing")
        assert page.status_code == 200 and b"instanced" in page.data and b"regex" in page.data
        r = client.post(
            "/admin/warden/sharing",
            data={"nonce": nonce(client), "action": "watch", "challenge_id": [str(chal), "9999"]},
        )
        assert b"Watching 1 challenge" in r.data
        r = client.post("/admin/warden/sharing", data={"nonce": nonce(client), "action": "scan"})
        assert b"Scan finished: 0" in r.data
    with app.app_context():
        assert sharing.watched() == {chal}


def test_admin_pages_render_and_save(app):
    user_id = player(app)
    with app.app_context():
        challenge_id = gen_challenge(db).id
    with login_as_user(app, name="admin") as client:
        for path in (
            "/admin/warden",
            "/admin/warden/activity",
            "/admin/warden/devices",
            "/admin/warden/sharing",
            "/admin/warden/fast-solves",
        ):
            assert client.get(path).status_code == 200, path

        form = {"nonce": nonce(client), "action": "features", "team_privacy": "on", "flag_lockout": "on"}
        assert b"Features saved" in client.post("/admin/warden", data=form).data
        r = client.post(
            "/admin/warden",
            data={
                "nonce": nonce(client),
                "action": "add-block",
                "challenge_id": challenge_id,
                "account_id": user_id,
            },
        )
        assert b"Challenge blocked" in r.data
        r = client.post(
            "/admin/warden",
            data={
                "nonce": nonce(client),
                "action": "lock-settings",
                "threshold": 2,
                "window": 60,
                "duration": 60,
            },
        )
        assert b"not saved" in r.data
    with app.app_context():
        assert settings.enabled("team_privacy") and settings.enabled("flag_lockout")
        assert not settings.enabled("client_activity")
        assert not settings.enabled("device_tracking")
        assert blocks.load_blocks() == {challenge_id: {f"u{user_id}"}}
        assert settings.lock_settings() == settings.LOCK_DEFAULTS


def test_admin_pages_are_admin_only(app):
    player(app)
    with login_as_user(app, name="player") as client:
        for path in (
            "/admin/warden",
            "/admin/warden/activity",
            "/admin/warden/devices",
            "/admin/warden/sharing",
            "/admin/warden/fast-solves",
        ):
            assert client.get(path).status_code in (302, 403), path


def test_admin_pages_survive_deleted_accounts(app):
    user_id = player(app)
    with login_as_user(app, name="player") as client:
        client.get("/api/v1/challenges", headers={"User-Agent": "curl/8.0"})
    with app.app_context():
        Users.query.filter_by(id=user_id).delete()
        db.session.commit()
    with login_as_user(app, name="admin") as client:
        assert client.get("/admin/warden/activity").status_code == 200
        assert client.get("/admin/warden").status_code == 200


def test_fast_solves_report_quick_and_unopened_solves(teams_app):
    app = teams_app
    with app.app_context():
        teams = {}
        for team_name, members in (("Red", ("r1", "r2")), ("Blue", ("b1",)), ("Green", ("g1",))):
            team = gen_team(db, name=team_name, email=f"{team_name}@example.test", member_count=0)
            teams[team_name] = team.id
            for name in members:
                gen_user(db, name=name, email=f"{name}@example.test", team_id=team.id, verified=True)
        chal = gen_challenge(db, name="hard").id
        gen_flag(db, challenge_id=chal, content="flag{hard}")
        welcome = gen_challenge(db, name="welcome").id
        gen_flag(db, challenge_id=welcome, content="flag{welcome}")
        assert fastsolves.since() is not None
    with login_as_user(app, name="r1") as client:
        assert client.get("/api/v1/challenges", headers=BROWSER).status_code == 200
        assert client.get(f"/api/v1/challenges/{chal}", headers=BROWSER).status_code == 200
    with login_as_user(app, name="r2") as client:
        client.get(f"/api/v1/challenges/{chal}", headers=BROWSER)
    with app.app_context():
        view = ChallengeView.query.one()
        assert view.account == f"t{teams['Red']}" and view.challenge_id == chal
        view.date -= timedelta(hours=2)
        db.session.commit()
    with login_as_user(app, name="r2") as client:
        assert submit(client, chal, "flag{hard}") == "correct"
    with login_as_user(app, name="b1") as client:
        client.get(f"/api/v1/challenges/{chal}", headers=BROWSER)
        assert submit(client, chal, "flag{hard}") == "correct"
        client.get(f"/api/v1/challenges/{welcome}", headers=BROWSER)
        assert submit(client, welcome, "flag{welcome}") == "correct"
    with login_as_user(app, name="g1") as client:
        assert submit(client, chal, "flag{hard}") == "correct"
    with app.app_context():
        found = {(r["solve"].team_id, r["solve"].challenge_id): r for r in fastsolves.rows()}
        assert set(found) == {
            (teams["Blue"], chal),
            (teams["Blue"], welcome),
            (teams["Green"], chal),
        }, "the slow solve and the listing request are not reported"
        assert found[(teams["Blue"], chal)]["seconds"] < 60
        assert found[(teams["Green"], chal)]["seconds"] is None
        assert found[(teams["Green"], chal)]["opened"] is None
        assert 3500 < found[(teams["Blue"], chal)]["median"] < 3700

        fastsolves.save_ignored([welcome])
        fastsolves.save_threshold(3 * 3600)
        found = {(r["solve"].team_id, r["solve"].challenge_id) for r in fastsolves.rows()}
        assert found == {(teams["Red"], chal), (teams["Blue"], chal), (teams["Green"], chal)}


def test_fast_solves_skip_solves_before_tracking_started(app):
    alice = player(app, name="alice")
    with app.app_context():
        chal = gen_challenge(db).id
        solve = gen_solve(db, user_id=alice, challenge_id=chal)
        solve.date = fastsolves.since() - timedelta(minutes=5)
        gen_solve(db, user_id=Users.query.filter_by(type="admin").first().id, challenge_id=chal)
        db.session.commit()
        assert fastsolves.rows() == [], "old solves and admin solves are not reported"
        fastsolves.start_tracking(reset=True)
        assert fastsolves.since() > solve.date


def test_fast_solves_admin_page(app):
    player(app, name="alice")
    with app.app_context():
        chal = gen_challenge(db, name="quickie").id
        gen_flag(db, challenge_id=chal, content="flag{q}")
    with login_as_user(app, name="alice") as client:
        client.get(f"/api/v1/challenges/{chal}", headers=BROWSER)
        assert submit(client, chal, "flag{q}") == "correct"
    with login_as_user(app, name="admin") as client:
        page = client.get("/admin/warden/fast-solves")
        assert page.status_code == 200 and b"quickie" in page.data and b"alice" in page.data
        r = client.post(
            "/admin/warden/fast-solves",
            data={"nonce": nonce(client), "action": "fast-settings", "seconds": "2"},
        )
        assert b"Not saved" in r.data
        r = client.post(
            "/admin/warden/fast-solves",
            data={"nonce": nonce(client), "action": "fast-settings", "seconds": "120", "ignore": [str(chal)]},
        )
        assert b"Fast solve settings saved" in r.data and b"No fast solves found" in r.data
    with app.app_context():
        assert fastsolves.threshold() == 120 and fastsolves.ignored() == {chal}
        assert Solves.query.count() == 1
