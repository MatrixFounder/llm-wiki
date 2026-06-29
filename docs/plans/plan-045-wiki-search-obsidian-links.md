# PLAN 045 — wiki-search Obsidian URI links

Single-file enhancement: `scripts/wiki_skills/wiki_search.py` gains `file_path` +
`obsidian_url` in JSON hits and an OSC 8 / plain-URL appendage in `--format markdown`.
No DDL. No new deps (stdlib `urllib.parse`). **Stub-First**: stubs + RED tests first,
implementation second.

---

## Atomic checklist (stub-first; Red → Green; each bead = one verifiable gate)

- **S1 — Branch + test file stub (R-8, RED gate).**
  Create branch `task-045-wiki-search-obsidian-links`.
  Create `tests/test_wiki_search_obsidian_links.py` with all **5 test functions as
  skeletons** (`pytest.mark.skip` or `assert False, "stub"`): 
  `test_search_json_includes_file_path_and_obsidian_url`,
  `test_search_json_obsidian_url_null_when_vault_unknown`,
  `test_search_json_vault_cache_called_once_per_unique_vault`,
  `test_search_markdown_tty_osc8_link`,
  `test_search_markdown_pipe_plain_url`.
  *Gate:* `pytest tests/test_wiki_search_obsidian_links.py` collects 5 tests,
  all SKIP/FAIL (not ERROR on import).

- **S2 — JSON output: `file_path` + `obsidian_url` (R-1, R-2, R-3, R-6, R-9, R-10).**
  In `scripts/wiki_skills/wiki_search.py`:
  (a) Add `from urllib.parse import quote as _url_quote` and
      `from scripts.wiki_index.models import Vault` (if not already imported via PageHit).
  (b) After `hits = _search(...)` / `repo.search_pages(...)` and before building `results`,
      build `vault_cache: dict[str, Vault | None]`:
      `{vid: repo.get_vault(vid) for vid in {h.page.vault_id for h in hits}}`.
  (c) Add helper `_obsidian_url(vault: Vault | None, file_path: str) -> str | None`:
      if vault is None → return None;
      vault_name = _url_quote(vault.root_path.name, safe='');
      file_enc = _url_quote(file_path, safe='/-_.~');
      return f"obsidian://open?vault={vault_name}&file={file_enc}".
  (d) Extend the `results` dict comprehension with:
      `"file_path": h.page.file_path,`
      `"obsidian_url": _obsidian_url(vault_cache.get(h.page.vault_id), h.page.file_path),`.
  Make the three JSON tests GREEN.
  *Gate:* `pytest tests/test_wiki_search_obsidian_links.py::test_search_json_*` (3 tests
  green); `pytest tests/` (all pre-existing tests green); no `import anthropic`.

- **S3 — Markdown format: OSC 8 + plain URL (R-4, R-5, R-9).**
  In the markdown format block (`args.format == "markdown"` branch) of `wiki_search.py`:
  (a) Detect TTY ONCE before the loop: `_is_tty = sys.stdout.isatty()`.
  (b) Build per-hit suffix: if `obsidian_url` is not None:
      - TTY: `suffix = f"  →  \033]8;;{obsidian_url}\033\\[↗]\033]8;;\033\\"`
      - non-TTY: `suffix = f"  →  {obsidian_url}"`
      else: `suffix = ""`.
  (c) Append `suffix` after the snippet on each `lines.append(...)` call.
  Make the two markdown tests GREEN.
  *Gate:* `pytest tests/test_wiki_search_obsidian_links.py` (ALL 5 green);
  `pytest tests/` (all pre-existing tests still green).

- **S4 — SKILL.md update (R-7).**
  Edit `skills/wiki-search/SKILL.md`:
  (a) In the JSON contract section ("Default output: JSON envelope with `hits[]`..."),
      add `file_path` and `obsidian_url` to the per-hit field list with their types and
      null condition.
  (b) Add a new paragraph below the contract section:
      ```
      **Obsidian deep-link (`obsidian_url`).** Each hit carries
      `obsidian_url: "obsidian://open?vault=<name>&file=<path>"` when the vault is
      registered (null otherwise). `<name>` is the vault root folder basename — the
      identifier Obsidian uses in its URI scheme (note: may differ from `vault_id` if
      the folder was renamed). `--format markdown` appends a clickable `[↗]` OSC 8
      hyperlink when stdout is a TTY, or the plain URI when piped.
      ```
  (c) Bump `version:` in the YAML frontmatter.
  *Gate:* skill file updated; `skill-validator` clean (run if available); version bumped.

- **S5 — Final validation: mypy + full test suite.**
  (a) `cd /Users/sergey/dev-projects/obsidian-llm-wiki && source .venv/bin/activate
      && mypy --strict scripts/wiki_skills/wiki_search.py` — must be clean.
  (b) `pytest tests/` — all tests green (including the 5 new ones).
  (c) `grep -r "import anthropic" scripts/wiki_skills/wiki_search.py` — must be empty.
  (d) Smoke-check: run `wiki-search "test" --format json --db-path <any sample db>` and
      verify `file_path` + `obsidian_url` appear in the output (or at least the keys exist
      with null values if no vault is registered for the sample).
  *Gate:* All gates above pass. Ready for VDD reviewer pass (`code-reviewer` +
  `critic-logic`).

---

## Coverage → RTM

| Bead | RTM |
|------|-----|
| S1 | R-8 (test stubs) |
| S2 | R-1, R-2, R-3, R-6, R-9, R-10, NF-1, NF-2 |
| S3 | R-4, R-5, R-9 |
| S4 | R-7 |
| S5 | R-8, R-9 (full validation) |
