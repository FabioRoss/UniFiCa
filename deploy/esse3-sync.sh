#!/bin/sh
# Import the latest ESSE3 snapshot published by the GitHub Action
# (.github/workflows/esse3-snapshot.yml, branch `esse3-data`).
#
# Run by cron on the server, e.g. hourly; it does nothing when there is no
# new snapshot. New sessions and changed dates are notified as usual.
# Every output line starts with the date and time, for the cron log.
set -u
cd "$(dirname "$0")/.."

run_sync() (
    set -e
    git fetch -q origin esse3-data
    git show origin/esse3-data:esse3-medicina.json > /tmp/openunifi-esse3.json
    # Its "Copying/Copied" lines only matter when the copy fails
    out=$(docker compose cp /tmp/openunifi-esse3.json openunifi-app:/tmp/esse3.json 2>&1) || { echo "$out"; exit 1; }
    docker compose exec -T openunifi-app python -m app.cli import-exams /tmp/esse3.json --sync
)

stamp() {
    while IFS= read -r line; do
        printf '%s %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$line"
    done
}

# sh has no pipefail: keep the exit code of run_sync, not of stamp
status=$(mktemp)
{ run_sync 2>&1; echo $? > "$status"; } | stamp
code=$(cat "$status")
rm -f "$status"
[ "$code" = 0 ] || echo "$(date '+%Y-%m-%d %H:%M:%S') ERRORE: sincronizzazione fallita (codice $code)"
exit "$code"
