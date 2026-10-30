# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

## [1.0.0] - 2026-10-30

First public release.

### Added

- Client activity: logging of self-identified AI agents, automation libraries, security tools,
  CTFd API tokens and in-page browser-automation marks, plus player token revocation.
- Shared devices: device-ID cookie and a list of devices used by several accounts or teams.
- Flag brute-force lockout per team (or user) and challenge, with configurable thresholds.
- Flag sharing: report the same unique flag (instancer or per-session regex flags) submitted by
  two accounts, live and by scanning past submissions.
- Fast solves: list players who solved several challenges in a short time, with configurable
  limits and ignored challenges.
- Team pages: one page per team (or player) with every signal Warden has about it, and a Teams
  tab that ranks teams by signals.
- Filters by player name, team name, challenge name and IP address on every admin page.
- Per-account challenge blocks with an admin UI.
- Optional team privacy filtering.
- `WARDEN_*` environment overrides for every feature switch.
- Install by cloning the repository into `CTFd/plugins/` (any folder name); works with any theme
  that renders `Plugins.scripts`, with no CTFd core or theme changes.

[Unreleased]: https://github.com/0xZyyz/ctfd-warden/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/0xZyyz/ctfd-warden/releases/tag/v1.0.0
