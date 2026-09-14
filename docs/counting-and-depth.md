# Counting, clustering, and depth

Three mechanisms that stop an audit being graded on how hard the model looked.
Summarised in the [README](../README.md#why-you-can-trust-the-number); the
details are here.

## The count is measured

Once a quote is verified, the scorer searches the whole tree for it and reports
every file it lands in. You file the defect once; the report says it is in
twenty-six files. Filing it twenty-six times earns nothing.

The sweep reads every text file git lists — tracked, plus untracked files that
are not ignored — once. It skips binaries and anything over 1 MB, and caps at
200 occurrences per quote. `--no-scan` opts out; `--fold-case` is honoured, so
the sweep always matches the way verification did.

Each kept finding gains `occurrences` (path and line for each hit),
`occurrence_count` and `files_affected`; the report gains a top-level
`blast_radius`.

## A root cause is charged once

The same defect is often worded differently in each place, which defeats
quote-based dedupe. Give those findings the same `cluster` id and they collapse
into one scored finding whose blast radius is the union of all their quotes:

```bash
bs-score examples/findings.blast.json --repo-root examples/fixture-repo --format md
# one root cause reported three ways → 1 finding, 3 points, 3 files affected
```

## A shallow audit says so

A payload can carry what it actually opened:

```json
{
  "audit": {
    "files_read": ["README.md", "src/cli.py", "src/api.py"],
    "notes": "Docs claims plus every module under src/."
  }
}
```

For `repo`, `pr`, `branch` and `skill` the report is stamped `shallow` when that
list holds no implementation file, and `unreported` when the block is missing.

A path in the list that does not exist earns **no credit**: it is excluded from
`files_read`, `code_files_read` and `coverage`, and named in `missing_files`. It
cannot turn a shallow pass into a deep one on its own — but if the audit also
read a real implementation file, the `status` under `depth` is still `deep`. The
field that accounts for the phantom is `sufficient`, and that is what
`--require-depth` gates on:

| audit block | `status` | `sufficient` | `--require-depth` |
|---|---|---|---|
| docs only | `shallow` | `false` | exit 1 |
| docs + a phantom "code" file | `shallow` | `false` | exit 1 |
| real code + a phantom file | `deep` | `false` | exit 1 |
| real code, all paths exist | `deep` | `true` | exit 0 |

```console
$ bs-score examples/findings.shallow.json --repo-root examples/fixture-repo --format md
- depth: **shallow** — 2 file(s) read, 0 of them implementation (20% of the tree); **1 listed file(s) do not exist**
- blast radius: 1 file(s) affected across 10 scanned
```
