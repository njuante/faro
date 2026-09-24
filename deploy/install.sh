#!/bin/sh
# Installs (or updates) faro on Debian/Ubuntu and similar, as a systemd service.
#
#   curl -fsSL https://raw.githubusercontent.com/njuante/faro/main/deploy/install.sh | sudo sh
#
# Or from a checkout:  sudo ./deploy/install.sh
#
# What it does: creates a `faro` system user, copies the code to /opt/faro,
# puts the config in /etc/faro/faro.toml (only the first time) and the data in
# /var/lib/faro, installs the `faro` command and starts the service on port 8080.
set -eu

REPO="${FARO_REPO:-njuante/faro}"
BRANCH="${FARO_BRANCH:-main}"
PREFIX=/opt/faro
CONF_DIR=/etc/faro
DATA_DIR=/var/lib/faro

say() { printf '\033[1m%s\033[0m\n' "$*"; }
die() { printf 'error: %s\n' "$*" >&2; exit 1; }

[ "$(id -u)" = 0 ] || die "run it as root (sudo)"
command -v python3 >/dev/null || die "python3 is required (apt install python3)"
python3 -c 'import sys; sys.exit(sys.version_info < (3, 11))' || die "python 3.11 or newer is required"
command -v ssh >/dev/null || { say "Installing the SSH client…"; apt-get install -y -qq openssh-client >/dev/null; }

# source: this checkout, or a fresh download
here=$(cd "$(dirname "$0")/.." 2>/dev/null && pwd || true)
if [ -n "$here" ] && [ -f "$here/faro/__init__.py" ]; then
  src="$here"
else
  tmp=$(mktemp -d)
  trap 'rm -rf "$tmp"' EXIT
  say "Downloading faro ($REPO@$BRANCH)…"
  curl -fsSL "https://github.com/$REPO/archive/refs/heads/$BRANCH.tar.gz" | tar -xz -C "$tmp" --strip-components=1
  src="$tmp"
fi

id faro >/dev/null 2>&1 || useradd --system --home-dir "$DATA_DIR" --shell /usr/sbin/nologin faro
install -d -o faro -g faro -m 0750 "$DATA_DIR" "$CONF_DIR"

say "Installing to $PREFIX…"
rm -rf "$PREFIX.new"
mkdir -p "$PREFIX.new"
cp -r "$src/faro" "$src/agent" "$src/web" "$src/faro.example.toml" "$PREFIX.new/"
rm -rf "$PREFIX" && mv "$PREFIX.new" "$PREFIX"

cat > /usr/local/bin/faro <<'WRAP'
#!/bin/sh
# faro command: always runs as the faro user, so keys and files keep the right owner
export PYTHONPATH=/opt/faro FARO_CONFIG="${FARO_CONFIG:-/etc/faro/faro.toml}"
if [ "$(id -u)" = 0 ]; then exec runuser -u faro -- python3 -m faro "$@"; fi
exec python3 -m faro "$@"
WRAP
chmod 755 /usr/local/bin/faro

cp "$src/deploy/faro.service" /etc/systemd/system/faro.service
systemctl daemon-reload

if [ ! -f "$CONF_DIR/faro.toml" ]; then
  say "Creating $CONF_DIR/faro.toml…"
  # read the password from the terminal even when this script arrives through a pipe
  if (exec < /dev/tty) 2>/dev/null; then /usr/local/bin/faro init < /dev/tty; else /usr/local/bin/faro init; fi
fi

systemctl enable --now faro >/dev/null 2>&1
systemctl restart faro
sleep 2
if ! systemctl is-active --quiet faro; then
  journalctl -u faro -n 15 --no-pager
  die "faro did not start: fix the error above in $CONF_DIR/faro.toml, then: systemctl restart faro"
fi
port=$(sed -n 's/^port *= *\([0-9]*\).*/\1/p' "$CONF_DIR/faro.toml" | head -1)
ip=$(hostname -I 2>/dev/null | cut -d' ' -f1)
say "faro is running: http://${ip:-localhost}:${port:-8080}"
echo "Add a server:   faro add-host root@192.168.1.20 --name nas"
echo "Edit services:  $CONF_DIR/faro.toml (changes apply by themselves)"
echo "Logs:           journalctl -u faro -f"
