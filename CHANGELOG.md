# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

## [1.0.0] - 2026-10-29

First public release, extracted from the anti-cheat plugin used at Securinets CTF Quals 2026.

### Added

- Client activity: logging of self-identified AI agents, automation libraries, security tools,
  CTFd API tokens and in-page browser-automation marks, plus player token revocation.
- Shared devices: device-ID cookie and a list of devices used by several accounts or teams.
- Flag brute-force lockout per team (or user) and challenge, with configurable thresholds.
- Per-account challenge blocks with an admin UI.
- Optional team privacy filtering and optional regional brackets (teams and users modes).
- Admin pages (Overview, Client activity, Shared devices) and `WARDEN_*` environment overrides.
- Works with any theme that renders `Plugins.scripts`; no CTFd core or theme changes needed.
