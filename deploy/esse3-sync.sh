#!/bin/sh
# Import the latest ESSE3 snapshot published by the GitHub Action
# (.github/workflows/esse3-snapshot.yml, branch `esse3-data`).
#
# Run by cron on the server, e.g. hourly; it does nothing when there is no
# new snapshot. New sessions and changed dates are notified as usual.
set -eu
cd "$(dirname "$0")/.."

git fetch -q origin esse3-data
git show origin/esse3-data:esse3-medicina.json > /tmp/openunifi-esse3.json
docker compose cp /tmp/openunifi-esse3.json openunifi-app:/tmp/esse3.json
docker compose exec -T openunifi-app python -m app.cli import-exams /tmp/esse3.json --sync
