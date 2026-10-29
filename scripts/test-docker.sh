#!/usr/bin/env sh
# Run Warden's tests inside the official CTFd image, so nothing has to be installed locally.
#   scripts/test-docker.sh            # CTFd 3.8.9
#   CTFD_VERSION=3.8.0 scripts/test-docker.sh -k lockout
set -eu

CTFD_VERSION="${CTFD_VERSION:-3.8.9}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

exec docker run --rm --user root \
  -v "$ROOT:/opt/CTFd/CTFd/plugins/warden:ro" \
  -v "$ROOT/tests:/opt/CTFd/tests/warden:ro" \
  -e PYTHONDONTWRITEBYTECODE=1 \
  --workdir /opt/CTFd \
  --entrypoint sh \
  "ctfd/ctfd:$CTFD_VERSION" \
  -c 'pip install -q --disable-pip-version-check pytest >/dev/null && python -m pytest -p no:cacheprovider -q tests/warden "$@"' \
  sh "$@"
