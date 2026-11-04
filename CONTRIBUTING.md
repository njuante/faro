# Contributing

Thanks for wanting to help. faro is small on purpose, so a few rules keep it
that way:

- **No new dependencies.** Server and agent use the Python standard library
  only. A change that needs `pip install` will not be merged.
- **The agent stays on Python 3.7+**, because it runs on whatever the
  monitored host has. CI checks it on 3.8–3.10.
- **Nothing listens on the hosts.** Features that need an open port on a
  monitored machine are out of scope.

## Before opening a pull request

```sh
python3 -m unittest discover -s tests -t .
ruff check .            # if you have ruff; CI runs it anyway
python3 -m faro demo    # look at your change at http://localhost:8080
```

Keep pull requests focused on one thing and say in the description how you
tested it. Screenshots help for anything visible.

## Reporting bugs

Open an issue with the faro version (`faro --version`), how you installed it
(script, Docker or checkout), the OS of the server and of the host involved,
and what the logs say (`journalctl -u faro -n 50`). Remove hostnames, IPs and
tokens you do not want public.

Security problems are not reported in issues: see [SECURITY.md](SECURITY.md).
