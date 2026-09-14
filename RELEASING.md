# Releasing

Owner-run; automation prepares, a human publishes.

1. **Bump the version** in `pyproject.toml` (`project.version`) and
   `src/bs_score/__init__.py` (`__version__`) — they must match.
2. **Update `CHANGELOG.md`**: move Unreleased items under the new version and
   date.
3. **Verify everything:**

   ```bash
   uv sync --extra dev
   uv run pytest
   uv run ruff check .
   uv run python scripts/gen_agent_wrappers.py --check
   uv run python scripts/check_receipts.py
   uv run python scripts/gen_llms_txt.py --check
   ```

4. **Build and inspect:**

   ```bash
   uv build
   tar -tf dist/*.tar.gz | head   # sdist carries src, tests, examples, data
   ```

5. **Publish** (needs your own PyPI credentials; never commit them):

   ```bash
   uv publish
   ```

6. **Tag and push:**

   ```bash
   git tag vX.Y.Z && git push --tags
   ```

After the first PyPI release, `uvx bs-score` works with no `--from`; update the
README install caveats and the per-runtime table note when that lands.
