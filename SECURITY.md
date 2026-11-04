# Security

faro holds SSH keys that can run its agent on your servers and, with the
Proxmox plugin, an API token that can power guests on and off. Security reports
are taken seriously.

## Reporting a vulnerability

Please **do not open a public issue**. Use GitHub's private reporting:
[Report a vulnerability](https://github.com/njuante/faro/security/advisories/new).

Include what you found, how to reproduce it and what an attacker could do with
it. You will get an answer within a week; a fix and a release follow as soon as
the issue is confirmed, and you are credited in the release notes unless you
prefer otherwise.

## Supported versions

Only the latest release gets security fixes. Update with the same install
command you used the first time.

## Scope

In scope: the faro server and web UI, the agent and its forced-command setup,
the installer and the plugins in this repository.

Out of scope: private plugins in `/etc/faro/plugins/`, weaknesses that need
someone who already has root on the faro server, and the public demo (it runs
made-up data with no real hosts).
