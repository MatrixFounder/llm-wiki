# TASK 045-03 — Markdown format: OSC 8 TTY link + plain URL (GREEN)

## Goal
Add the OSC 8 hyperlink (TTY) and plain URL (non-TTY) suffix to the `--format markdown`
output branch in `scripts/wiki_skills/wiki_search.py`, and make the 2 markdown test
cases GREEN.

## Context
- Primary file to edit: `scripts/wiki_skills/wiki_search.py`
- The markdown-format block starts at `if args.format == "markdown":` (around line 222)
- The `obsidian_url` per-hit is now computed in S2 (task-045-02) via `vault_cache`
- Tests to make GREEN: `test_search_markdown_tty_osc8_link` and
  `test_search_markdown_pipe_plain_url` in `tests/test_wiki_search_obsidian_links.py`

## Steps

### Step 1: Detect TTY and build per-hit suffix

In the `if args.format == "markdown":` block, replace the existing loop:
```python
lines = [f'## {heading} — {len(results)} hits', ""]
for r in results:
    lines.append(
        f"- [[{r['vault_id']}:{r['project']}/{r['slug']}|{r['title']}]] "
        f"(BM25={r['bm25_score']:.2f}) — \"{r['snippet']}\""
    )
```
with:
```python
_is_tty = sys.stdout.isatty()
lines = [f'## {heading} — {len(results)} hits', ""]
for r in results:
    obs_url: str | None = r["obsidian_url"]
    if obs_url is not None:
        if _is_tty:
            suffix = f"  →  \033]8;;{obs_url}\033\\[↗]\033]8;;\033\\"
        else:
            suffix = f"  →  {obs_url}"
    else:
        suffix = ""
    lines.append(
        f"- [[{r['vault_id']}:{r['project']}/{r['slug']}|{r['title']}]] "
        f"(BM25={r['bm25_score']:.2f}) — \"{r['snippet']}\"{suffix}"
    )
```

Unicode note: `→` = `→`, `↗` = `↗`

### Step 2: Fill in the 2 markdown test functions

Replace the 2 markdown stub functions in `tests/test_wiki_search_obsidian_links.py`:

```python
def test_search_markdown_tty_osc8_link(
    vault_db: tuple[Path, Path], capsys: pytest.CaptureFixture[str],
) -> None:
    """--format markdown on TTY appends OSC 8 hyperlink (R-4)."""
    _, db = vault_db
    with patch("sys.stdout") as mock_stdout:
        mock_stdout.isatty.return_value = True
        mock_stdout.write = capsys.readouterr  # redirect capture
        # Use StringIO to capture output properly
        import io
        buf = io.StringIO()
        mock_stdout.write = buf.write
        mock_stdout.fileno = lambda: 1  # satisfy any fileno checks

    # Simpler approach: patch isatty on the real sys.stdout
    with patch("sys.stdout.isatty", return_value=True):
        rc = wiki_search.main(
            ["foo", "--vaults", VAULT_ID, "--db-path", str(db), "--format", "markdown"]
        )
    assert rc == 0
    out = capsys.readouterr().out
    # OSC 8 start and closing terminator must both be present
    assert "\033]8;;obsidian://" in out, f"Missing OSC 8 start in: {out!r}"
    assert "\033]8;;\033\\" in out, f"Missing OSC 8 terminator in: {out!r}"


def test_search_markdown_pipe_plain_url(
    vault_db: tuple[Path, Path], capsys: pytest.CaptureFixture[str],
) -> None:
    """--format markdown when piped appends plain URL, no ANSI escapes (R-5)."""
    _, db = vault_db
    with patch("sys.stdout.isatty", return_value=False):
        rc = wiki_search.main(
            ["foo", "--vaults", VAULT_ID, "--db-path", str(db), "--format", "markdown"]
        )
    assert rc == 0
    out = capsys.readouterr().out
    assert "obsidian://open?vault=" in out, f"Missing plain URL in: {out!r}"
    assert "\033]8;;" not in out, f"Unexpected ANSI escape in: {out!r}"
```

### Step 3: Verify gate

```bash
source .venv/bin/activate
pytest tests/test_wiki_search_obsidian_links.py -v
# Expected: 5 PASSED (all green after S2 + S3)
pytest tests/ -q --tb=short
# No regressions
```

## Verification
```bash
source .venv/bin/activate
pytest tests/test_wiki_search_obsidian_links.py -v
# 5 PASSED
```
