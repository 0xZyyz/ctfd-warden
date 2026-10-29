# Contributing to Warden

Thanks for helping. Bug reports, new detection signatures and fixes are all welcome.

## Layout

```
warden/                  the plugin: this folder is what organisers copy into CTFd/plugins/
  __init__.py            load() and the request hooks, which call each feature in order
  settings.py            feature switches (admin page, WARDEN_* env vars) and numeric settings
  activity.py            client activity logging and /warden/client-signal
  detection.py           User-Agent / header classification (AI agents, automation, tools)
  devices.py             device-ID cookie and shared-device records
  lockout.py             flag brute-force lockout
  blocks.py              per-account challenge blocks
  privacy.py             team privacy response filtering
  brackets.py            regional brackets
  admin.py               the three admin pages
  models.py, migrations/ database tables (alembic, run by CTFd on startup)
  templates/, assets/    admin page templates and the automation-signal script
tests/warden/            pytest suite, run from inside a CTFd checkout
scripts/test-docker.sh   runs the suite in the official ctfd/ctfd image
```

## Running the tests

```sh
scripts/test-docker.sh                      # CTFd 3.8.9
CTFD_VERSION=3.8.0 scripts/test-docker.sh   # another release
scripts/test-docker.sh -k brackets -x       # pass pytest arguments through
```

The script mounts `warden/` and `tests/warden/` into the image, so you only need Docker. To try your
change by hand, run `docker compose up` and open <http://localhost:8000>.

## Guidelines

- **Keep it drop-in.** Warden must work by copying one folder into `CTFd/plugins/`: no CTFd core
  patches, no required theme changes, no extra Python dependencies.
- **Fail open for players, closed for privacy.** A Warden bug must not turn a player's successful
  request into an error page (see `_after_request`), but the team privacy filter must never leak.
- **Signals are hints.** New detection entries go in `detection.py` with a test in
  `tests/warden/test_units.py`. Prefer specific needles; short ones (5 characters or fewer) only
  match at a word boundary.
- **Schema changes** need a new migration in `warden/migrations/` whose `down_revision` is the
  latest one. Never edit a released migration.
- **New settings** go in `settings.py`, stored in CTFd's config table under a `warden_` key.
- Add or update tests for behaviour changes, and a line in `CHANGELOG.md` under *Unreleased*.

## Pull requests

1. Fork, then create a branch from `main`.
2. Make the change with tests; `scripts/test-docker.sh` must pass.
3. Open a pull request describing what changed and why.

Security issues: please follow [SECURITY.md](SECURITY.md) instead of opening a public issue.
