# Examples

Six worked audits plus the repository's own v1 audit. Each `findings.*.json` has
a committed `score.*.json` receipt that CI reproduces byte-for-byte
(`scripts/check_receipts.py`).

The quotes point at real text, so verification has something to verify:

| directory | what it holds |
|-----------|---------------|
| `fixture-repo/` | A deliberately dishonest toy project — the README lies and the code is buggy |
| `fixture-prompts/` | Two flawed prompts for the `prompt` review type |
| `fixture-review/review.json` | A PR review body and comment, as a `--sources` manifest |

```bash
uv run bs-score findings.valid.json  --repo-root fixture-repo                     # 17
uv run bs-score findings.review.json --repo-root fixture-repo \
    --sources fixture-review/review.json                                          # 10
uv run bs-score findings.skill.json  --repo-root fixture-repo                     # 7
uv run bs-score findings.agent.json  --repo-root fixture-repo                     # 6
uv run bs-score findings.prompt.json --sources fixture-prompts                    # 18
uv run bs-score findings.hallucinated.json --repo-root fixture-repo               # 0
```

(The committed receipts are produced from the repository root — see
`scripts/check_receipts.py` for the exact invocations.)

## The two that matter

**`findings.hallucinated.json`** is four confident fabrications: a race condition
in a file with no async code, a token in a module that does not exist, a README
flag never mentioned, and a real line attributed to the wrong file. It scores
**0**. Under the v1 scorer it scored 14.

**`findings.self.json`** is the v1 audit of *this* repository — the eight defects
that v2 fixed. Every quote is now gone, so it scores **0** too. It is kept as a
regression gate: reintroduce one of those defects and its quote verifies again,
the score rises, and `--fail-over 0` fails CI.

## Repo/PR audits

Two passes: claims, then a deep code pass. Review audits: one finding per failure
mode. Prompt audits: register the prompts with `--sources` so their quotes are
checked like code.
