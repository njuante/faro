#!/bin/sh
# Installs the faro agent by hand, for hosts faro cannot reach with a password.
# `faro agent-command` prints this line with your key already in it:
#
#   curl -fsSL https://raw.githubusercontent.com/njuante/faro/main/deploy/install-agent.sh | sh -s -- "ssh-ed25519 AAAA… faro@server"
#
# Run it as the user faro will connect as (root gives disk health and Proxmox details).
set -eu
key="${1:-}"
case "$key" in ssh-ed25519\ *|ssh-rsa\ *|ecdsa-*) ;; *) echo "usage: install-agent.sh \"<faro's public key>\"" >&2; exit 2;; esac
REPO="${FARO_REPO:-njuante/faro}"
command -v python3 >/dev/null 2>&1 || { echo "faro: python3 is required (e.g. apt install python3)" >&2; exit 3; }
if [ "$(id -u)" = 0 ]; then dir=/usr/local/lib/faro; else dir="$HOME/.local/lib/faro"; fi
mkdir -p "$dir"
curl -fsSL "https://raw.githubusercontent.com/$REPO/main/agent/faro-agent.py" -o "$dir/faro-agent.py.new"
chmod 755 "$dir/faro-agent.py.new"
mv "$dir/faro-agent.py.new" "$dir/faro-agent.py"
umask 077
mkdir -p "$HOME/.ssh"
touch "$HOME/.ssh/authorized_keys"
body=$(echo "$key" | cut -d' ' -f2)
grep -vF "$body" "$HOME/.ssh/authorized_keys" > "$HOME/.ssh/authorized_keys.faro" || true
echo "command=\"python3 $dir/faro-agent.py\",restrict $key" >> "$HOME/.ssh/authorized_keys.faro"
mv "$HOME/.ssh/authorized_keys.faro" "$HOME/.ssh/authorized_keys"
command -v smartctl >/dev/null 2>&1 || echo "faro: tip: install smartmontools to see disk health" >&2
echo "faro: agent installed in $dir. That key can only run the agent: no shell, no forwarding."
