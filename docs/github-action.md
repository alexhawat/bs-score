# GitHub Action recipes

The composite action is [`action.yml`](../action.yml). Minimum usage:

```yaml
- uses: alexhawat/bs-score@main
  with:
    findings: findings.json
    fail-over: "10"
```

Inputs: `findings`, `repo-root`, `sources`, `fail-over`, `require-depth`,
`no-scan`, `baseline`, `format`, `ref`. Outputs: `score`, `band`, `report`.

`ref` selects the revision of this repository the scorer is installed from. It
defaults to the ref the action itself was resolved at, so pinning the action
pins the scorer with it:

```yaml
- uses: alexhawat/bs-score@8f0c1d2   # the scorer is installed from 8f0c1d2 too
```

Set it explicitly only to run a different revision of the scorer than the
action. It falls back to `main` when the action runs from a local path
(`uses: ./`), where GitHub provides no ref.

The scorer is installed from the repository the action itself was resolved
from (`github.action_repository`), so a fork runs its own scorer — not the
upstream repo's — at the same ref.

## Post the Markdown report as a PR comment

```yaml
- uses: alexhawat/bs-score@main
  with: { findings: findings.json, format: md }
- uses: actions/github-script@v7
  if: always()
  with:
    script: |
      const fs = require('fs');
      await github.rest.issues.createComment({
        owner: context.repo.owner, repo: context.repo.repo,
        issue_number: context.issue.number,
        body: fs.readFileSync('report.md', 'utf8'),
      });
```

## Upload findings to code scanning

```yaml
- uses: alexhawat/bs-score@main
  with: { findings: findings.json, format: sarif }
- uses: github/codeql-action/upload-sarif@v3
  with: { sarif_file: report.sarif }
```
