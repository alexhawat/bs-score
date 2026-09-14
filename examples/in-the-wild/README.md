# In the wild

Audits of small, realistic artifacts in the shape of real public ones — tiny
packages at an old tag, the kind of README that drifts ahead of its code.
These snapshots are synthetic-but-realistic stand-ins (naming no real project
avoids quoting anyone out of context); the pattern is the one you will meet in
the wild: docs written for a version the code has not caught up with.

| snapshot | audited as | score | lies caught |
|----------|-----------|------:|--------------|
| `tinycache/` | `repo` | 8 | "thread-safe", "LRU eviction", "TTL" — none implemented |
| `greetcli/` | `docs` | 10 | Python 3.8 promise vs `>=3.10`, a `--shout` flag that does not exist |

```bash
uv run bs-score ../findings.wild-tinycache.json --repo-root tinycache   # 8
uv run bs-score ../findings.wild-greetcli.json --repo-root greetcli     # 10
```

(From the repository root, use `--repo-root examples/in-the-wild/tinycache`
etc. — see `scripts/check_receipts.py` for the exact receipt invocations.)

To audit a real project, point `--repo-root` at its checkout and file the
findings your agent produces against the matching checklist. Both snapshots
here are also checkable mechanically:

```bash
bs-score claims greetcli/README.md --repo-root greetcli
```
