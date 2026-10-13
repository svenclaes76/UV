#!/usr/bin/env bash
# Offsite backup of Uvalu's data to a Hetzner Storage Box with borg
# (docs/deployment.md step 7). Runs daily from uvalu-backup.timer.
#
# Retention: archives older than 29 days are pruned on every run, so data
# removed from the app (account deletion) is gone from the offsite copies
# within 30 days, as privacy notice §8 promises. Keep the Storage Box's own
# automatic snapshots off, or they would keep it longer.
#
# Never backs up .env: the master secrets are kept offline, separately
# (docs/deployment.md, "Keep an offline copy").
set -euo pipefail

# /etc/uvalu/backup.env sets BORG_REPO, e.g.
#   BORG_REPO=ssh://u123456@u123456.your-storagebox.de:23/./uvalu
# shellcheck disable=SC1091
source /etc/uvalu/backup.env
export BORG_REPO
export BORG_PASSCOMMAND="cat /etc/uvalu/borg.pass"
export BORG_RSH="ssh -i /etc/uvalu/storagebox_ed25519 -o BatchMode=yes"

cd /opt/uvalu
borg create --stats --compression zstd \
    --exclude 'data/migration-snapshots' \
    "::{hostname}-{now:%Y-%m-%dT%H:%M}" \
    data .cache/users.json

borg prune --keep-within 29d
borg compact
