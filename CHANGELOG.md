# Changelog

All notable changes to faro are listed here. Versions follow
[Semantic Versioning](https://semver.org/); before 1.0, a minor version may
change the config format, and the notes say how to migrate.

## [Unreleased]

### Added
- The installer installs the latest release by default; `FARO_VERSION`
  picks a specific one (`FARO_BRANCH` still works).
- Release workflow: a `v*` tag creates the GitHub release from this file and
  publishes the Docker image to `ghcr.io/njuante/faro`.
- `CONTRIBUTING.md` and `SECURITY.md`.

## [0.1.0]

First public version.

- Server and agent with the Python standard library only (server 3.11+,
  agent 3.7+).
- Agents over SSH with a key pinned to a forced command: no open ports on
  the hosts. `faro add-host` installs and restricts the agent in one step.
- Live CPU, temperatures, memory, network, disks with SMART, ZFS pools,
  Proxmox guests, storages and backups, Docker containers.
- HTTP, TCP and DNS checks for services, with alerts (hysteresis, recovery
  message) to ntfy, Discord, Slack or a webhook.
- Plugins: Proxmox power buttons, Jellyfin/Plex/Navidrome cards, speed test,
  automations. Optional local AI assistant with read-only tools.
- PWA for phones, light and dark mode, English and Spanish.
- Demo mode (`python3 -m faro demo`) and a public demo.

[Unreleased]: https://github.com/njuante/faro/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/njuante/faro/releases/tag/v0.1.0
