"""Fast tests that need Flask but not a CTFd database."""

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from flask import Flask, jsonify

from CTFd.plugins.warden import privacy
from CTFd.plugins.warden.detection import classify_client


@pytest.mark.parametrize(
    "ua,kind",
    [
        ("Mozilla/5.0 Botim/1.0", None),
        ("superagent/1.0", "automation"),
        ("Codex/1.0", "ai"),
        ("curl/8.0", "automation"),
        ("python-requests/2.32", "automation"),
        ("Mozilla/5.0 (compatible; ClaudeBot/1.0)", "ai"),
        ("Mozilla/5.0 Chrome/130", None),
        ("", "automation"),
    ],
)
def test_client_classification_boundaries(ua, kind):
    with Flask(__name__).test_request_context(
        headers={"User-Agent": ua, "Accept-Language": "en"}
    ):
        result = classify_client()
        assert (result[0] if result else None) == kind


def test_browser_user_agent_without_accept_language_is_automation():
    with Flask(__name__).test_request_context(headers={"User-Agent": "Mozilla/5.0 Chrome/130"}):
        assert classify_client() == ("automation", "browser UA without Accept-Language")


def test_headless_client_hint_is_automation():
    headers = {
        "User-Agent": "Mozilla/5.0 Chrome/130",
        "Accept-Language": "en",
        "Sec-CH-UA": '"HeadlessChrome";v="130"',
    }
    with Flask(__name__).test_request_context(headers=headers):
        assert classify_client()[0] == "automation"


def test_api_token_is_flagged_whatever_the_user_agent():
    headers = {
        "Authorization": "Token abc",
        "User-Agent": "Mozilla/5.0 Chrome/130",
        "Accept-Language": "en",
    }
    with Flask(__name__).test_request_context(headers=headers):
        assert classify_client() == ("api-token", "API token")


def test_signature_headers_are_not_treated_as_verified_ai():
    with Flask(__name__).test_request_context(headers={"Signature-Input": "invented"}):
        kind, label = classify_client()
        assert kind == "automation" and "unverified" in label


class TestTeamPrivacy:
    def filter(self, path, data, team_id=None, admin=False, teams=True):
        original = deepcopy(data)
        app = Flask(__name__)
        with (
            app.test_request_context(path),
            patch.object(privacy, "is_admin", return_value=admin),
            patch.object(privacy, "authed", return_value=team_id is not None),
            patch.object(
                privacy, "get_current_user", return_value=SimpleNamespace(team_id=team_id)
            ),
            patch.object(privacy, "teams_mode", return_value=teams),
        ):
            response = jsonify(success=True, data=data)
            privacy.after_request(path, response)
            result = response.get_json()["data"]
        assert data == original, "shared cached data must stay unchanged"
        return result

    def test_team_profile_and_directory(self):
        team = {"id": 2, "name": "Other", "country": "TN", "members": [7, 8], "captain_id": 7}
        public = {"id": 2, "name": "Other"}
        for viewer in (None, 1):
            assert self.filter("/api/v1/teams/2", team, viewer) == public
            assert self.filter("/api/v1/teams", [team], viewer) == [public]
        assert self.filter("/api/v1/teams/2", team, 2) == team
        assert self.filter("/api/v1/teams/2", team, admin=True) == team

    def test_scoreboard_for_every_viewer(self):
        rows = [
            {"account_id": 1, "score": 100, "members": [3, 4]},
            {"account_id": 2, "score": 50, "members": [5]},
        ]
        for viewer in (2, None, 1):
            for row in self.filter("/api/v1/scoreboard", rows, viewer):
                assert ("members" in row) == (row["account_id"] == viewer)
        assert self.filter("/api/v1/scoreboard", rows, admin=True) == rows

    def test_solves_awards_and_graph_do_not_identify_members(self):
        solve = {"user_id": 7, "user": {"id": 7, "name": "Private"}, "team_id": 2, "value": 100}
        public = {"team_id": 2, "value": 100}
        for suffix in ("solves", "awards"):
            assert self.filter("/api/v1/teams/2/" + suffix, [solve], 1) == [public]
            assert self.filter("/api/v1/teams/2/" + suffix, [solve], 2) == [solve]
        graph = {"1": {"id": 2, "solves": [solve]}}
        assert self.filter("/api/v1/scoreboard/top/10", graph, 1) == {
            "1": {"id": 2, "solves": [public]}
        }
        assert self.filter("/api/v1/scoreboard/top/10", graph, 2) == graph
        assert self.filter("/api/v1/scoreboard/top/10", graph, teams=False) == graph

    @pytest.mark.parametrize("query", ["country=TN", "field=country&q=TN"])
    def test_country_filter_cannot_be_used_to_infer_country(self, query):
        from werkzeug.exceptions import Forbidden

        with (
            Flask(__name__).test_request_context("/api/v1/teams?" + query),
            patch.object(privacy, "is_admin", return_value=False),
        ):
            with pytest.raises(Forbidden):
                privacy.before_request("/api/v1/teams")
