# GitHub Action recipes

The composite action is [`action.yml`](../action.yml). Minimum usage:

```yaml
- uses: alexhawat/bs_score@main
  with:
    findings: findings.json
    fail-over: "10"
```

Inputs: `findings`, `repo-root`, `sources`, `fail-over`, `require-depth`,
`no-scan`, `baseline`, `format`, `ref`. Outputs: `score`, `band`, `report`.

> `ref` selects the revision of this repository the scorer is installed from,
> and defaults to `main`. Pinning the action (`alexhawat/bs_score@<sha>`) does
> **not** pin the scorer — pass `ref` with the same revision if you need both
> pinned together.

## Post the Markdown report as a PR comment

```yaml
- uses: alexhawat/bs_score@main
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
- uses: alexhawat/bs_score@main
  with: { findings: findings.json, format: sarif }
- uses: github/codeql-action/upload-sarif@v3
  with: { sarif_file: report.sarif }
```
