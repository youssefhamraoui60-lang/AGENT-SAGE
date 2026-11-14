#!/usr/bin/env bash
# Execute only on the new dedicated Ubuntu VM, never on Windows or an existing shared host.
set -euo pipefail
[[ $EUID -eq 0 ]] || { echo 'Run with sudo on the dedicated VM' >&2; exit 1; }
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 ]] || { echo 'This script targets Ubuntu 24.04 LTS' >&2; exit 1; }
if command -v docker >/dev/null; then
  docker info >/dev/null
  docker compose version
  echo 'Existing Docker preserved; no reinstall or configuration change.'
  exit 0
fi
for package in docker.io docker-compose docker-compose-v2 podman-docker containerd runc; do
  if dpkg-query -W -f='${Status}' "$package" 2>/dev/null | grep -q 'install ok installed'; then
    echo "Conflicting existing package $package; automatic removal refused" >&2
    exit 1
  fi
done
[[ ! -e /etc/apt/sources.list.d/docker.sources && ! -e /etc/apt/keyrings/docker.asc ]] || {
  echo 'Existing Docker repository configuration; inspect manually rather than overwrite' >&2; exit 1;
}
apt-get update
apt-get install -y ca-certificates curl
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
cat > /etc/apt/sources.list.d/docker.sources <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: noble
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF
apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
# New dedicated installation only: explicit startup, no startup on VM boot.
systemctl disable docker.service docker.socket containerd.service
systemctl start docker
docker info
docker compose version
dpkg-query -W docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
