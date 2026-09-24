# Architecture

```
agent/faro-agent.py     one file, copied to each host; prints one JSON line per second
faro/
  config.py             loads faro.toml, resolves env:/file: secrets, validates, filters what the browser sees
  hosts.py              one SSH subprocess per host; 15 min at 1 s + 24 h at 1 min of history
  checks.py             HTTP / TCP / DNS probes in parallel
  alerts.py             rules with a grace period and hysteresis; ntfy / webhook notifiers; alert log
  auth.py               PBKDF2 passwords, hashed server-side sessions, per-IP throttling
  web.py                stdlib HTTP server: static files, JSON API, Server-Sent Events
  plugins/              plugin loader and the built-in Proxmox plugin
  app.py                wires everything together
  cli.py                serve · demo · init · add-host · set-password · check · test-notify
  demo.py               made-up hosts for trying it out and for screenshots
web/                    vanilla JS modules and one stylesheet; no build step
deploy/                 installer, systemd unit, manual agent installer
```

## Decisions

**SSH instead of an HTTP agent.** Every homelab already has SSH, and a forced
command in `authorized_keys` (`command="…",restrict`) is a well-understood way to
give a key exactly one thing to do. The agent needs no port, no TLS certificate
and no token. The host is reached from faro only, and a stolen key can't do
anything except run the agent. The trade-off is that faro has to be able to reach
the hosts. A push mode for hosts behind NAT is on the roadmap.

**A long-lived stream instead of polling.** The agent keeps running and writes a
line per second, so rates (CPU, network, disk I/O) are computed from consecutive
readings on the host, and the slower collectors (SMART every 60 s, guests every
5 s) run in their own threads without blocking the fast ones. If the connection
drops, faro reconnects with exponential backoff.

**Standard library only.** Nothing to install means nothing to update, no supply
chain and no virtualenv on the hosts. The price is writing a few small things by
hand: the HTTP router, the chart and the TOML writing for `add-host`, which only
ever appends blocks.

**Config as the single source of truth.** The UI never keeps state that the
config doesn't have. Changing the file restarts the process through `execv`
after validating the new version, which keeps reload logic trivial.

**Alerts that don't cry wolf.** Each rule has a grace period (`service_down_after`)
and temperature/space rules have a few degrees or percent of hysteresis. Each
alert has a key, and an alert is only sent again after the problem clears.
