#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
[[ $EUID -eq 0 ]] || { echo 'Run using sudo on the dedicated VM' >&2; exit 1; }
umask 077
dc=(docker compose -f compose.yaml -f compose.ubuntu-vm.yaml)
id="$(date -u +%Y%m%dT%H%M%SZ)-$$"
destination="backups/$id"
mkdir -p "$destination"
running_n8n="$("${dc[@]}" ps --status running -q n8n)"
restore_n8n() { if [[ -n "$running_n8n" ]]; then "${dc[@]}" start n8n; fi; }
trap restore_n8n EXIT
"${dc[@]}" stop n8n
"${dc[@]}" exec -T postgres sh -ec 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$destination/backend.dump"
"${dc[@]}" exec -T postgres sh -ec 'pg_dump -U "$POSTGRES_USER" -d n8n -Fc' > "$destination/n8n.dump"
"${dc[@]}" cp n8n:/home/node/.n8n "$destination/n8n-home"
cp .env "$destination/environment.env"
cp compose.yaml compose.ubuntu-vm.yaml "$destination/"
cp -r database workflows "$destination/"
tar -czf "$destination/source.tar.gz" --exclude='./backups' --exclude='./logs' --exclude='./.git' --exclude='./.tools' --exclude='./backend/.venv' --exclude='./models' --exclude='./.env' .
(cd "$destination" && find . -type f ! -name SHA256SUMS -print0 | sort -z | xargs -0 sha256sum > SHA256SUMS)
tar -czf "backups/$id.tar.gz" -C backups "$id"
echo "Backup created: backups/$id.tar.gz (contains secrets; keep private)"
