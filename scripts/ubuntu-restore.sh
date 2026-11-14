#!/usr/bin/env bash
# Run from a NEW project directory, with the original secret .env restored first.
set -euo pipefail
cd "$(dirname "$0")/.."
[[ $EUID -eq 0 ]] || { echo 'Run using sudo on the new dedicated VM' >&2; exit 1; }
[[ $# -eq 1 && -d $1 ]] || { echo 'Argument: extracted backup directory' >&2; exit 1; }
backup="$(realpath "$1")"
docker info >/dev/null
(cd "$backup" && sha256sum -c SHA256SUMS)
cmp --silent .env "$backup/environment.env" || { echo 'Restore the original .env first; secrets differ' >&2; exit 1; }
# Only a fresh Compose project may be restored. Never overwrite an existing volume.
for suffix in pgdata n8ndata; do
  if docker volume inspect "agent-sage-x3_$suffix" >/dev/null 2>&1; then
    echo "Existing volume agent-sage-x3_$suffix: restore refused" >&2; exit 1
  fi
done
dc=(docker compose -f compose.yaml -f compose.ubuntu-vm.yaml)
"${dc[@]}" config --quiet
"${dc[@]}" up -d --wait postgres
"${dc[@]}" exec -T postgres sh -ec 'pg_restore --exit-on-error --clean --if-exists -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < "$backup/backend.dump"
"${dc[@]}" exec -T postgres sh -ec 'pg_restore --exit-on-error --clean --if-exists -U "$POSTGRES_USER" -d n8n' < "$backup/n8n.dump"
"${dc[@]}" create n8n
"${dc[@]}" cp "$backup/n8n-home/." n8n:/home/node/.n8n
"${dc[@]}" run --rm --no-deps --user root --cap-add CHOWN --entrypoint chown n8n -R 1000:1000 /home/node/.n8n
"${dc[@]}" up -d --wait postgres n8n
echo 'Restore commands finished. Run integration tests; this alone does not validate restoration.'
