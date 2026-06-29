# TASK 045 — wiki-search: native Obsidian URI links in CLI output

## 0. Meta
- **Task ID:** 045 · **Slug:** `task-045-wiki-search-obsidian-links`
- **Mode:** VDD — small scope, single file change. Reviewers: `code-reviewer` +
  `critic-logic` (URL encoding, null-safety, multi-vault lookup). `mypy --strict
  scripts/` is the static contract.
- **ADR:** None new. Reads existing `Vault.root_path` and `Page.file_path` (Class B
  fields, already in the DAL model) — zero schema change.
- **Touches:**
  - `scripts/wiki_skills/wiki_search.py` — primary: vault lookup cache, URL builder,
    `file_path` + `obsidian_url` in JSON results dict, OSC 8 link in markdown format.
  - `skills/wiki-search/SKILL.md` — JSON schema section updated; markdown-format
    behavior documented; obsidian URI format noted.
  - `tests/` — unit tests for new fields + URL construction + TTY/non-TTY branches.
- **Branch:** `task-045-wiki-search-obsidian-links`
- **Schema:** `user_version` 7, untouched. **Zero DDL. Zero new Python runtime deps.**

---

## 1. Problem / motivation

`wiki-search` results — both the JSON envelope and `--format markdown` output — currently
include `vault_id`, `slug`, `project`, `type`, `title`, `bm25_score`, and `snippet`. They do
NOT include the file path or any clickable link to open the page in Obsidian.

This means that after finding a relevant page the operator must manually construct the path and
open Obsidian separately. The `Page.file_path` field (relative to vault root) and
`Vault.root_path` are ALREADY in the DAL — we just don't surface them.

Adding:
1. `file_path` to the JSON hits (always) — the existing consumers can use it for `Read`,
   `Glob`, etc. without guessing the path.
2. `obsidian_url` to the JSON hits (when the vault name is resolvable) — a ready-to-use
   `obsidian://open?vault=<name>&file=<path>` deep-link.
3. ANSI OSC 8 clickable hyperlinks in `--format markdown` when stdout is a TTY (iTerm2,
   VS Code integrated terminal, most modern macOS terminals support OSC 8 link sequences).
   When piped (non-TTY) the plain URL is appended as text.

This is an **additive** change: no existing JSON field changes shape, no output is removed,
no schema is modified.

---

## 2. Scope

### In scope
- `file_path: str` added to every hit object in the JSON results dict.
- `obsidian_url: str | None` added to every hit object in JSON results. Value is:
  - `"obsidian://open?vault=<vault_name>&file=<url_encoded_path>"` when the vault is
    found in the registry (`repo.get_vault(vault_id)` returns a non-None `Vault`).
  - `null` when the vault is not found (stale registry, removed vault) or when the
    sentinel `_global_` is the `vault_id` in scope (edge-case guard).
- **Vault name resolution**: `vault_name = vault.root_path.name` (the folder basename).
  This is what Obsidian uses as the vault identifier in the URI.
- **Vault lookup cache**: build `vault_cache: dict[str, Vault | None]` inside `main()`
  before serialising results, keyed by `vault_id`; call `repo.get_vault(vault_id)` once
  per unique `vault_id` across all hits (not once per hit).
- **URL encoding**: `urllib.parse.quote(file_path, safe='/-_.~')` — forward slashes and
  dots kept unencoded so the path is human-readable in the terminal; special chars in
  folder/file names are percent-encoded.
- **Markdown format — TTY branch** (`sys.stdout.isatty() is True`):
  Replace the plain title text in the existing wikilink with an ANSI OSC 8 hyperlink
  wrapping the title, then show the wikilink+BM25+snippet as before.
  ANSI OSC 8 format: `\033]8;;<url>\033\\<title>\033]8;;\033\\`
  If `obsidian_url` is None (vault unknown) → title rendered without ANSI decoration.
- **Markdown format — non-TTY branch** (stdout is a pipe/redirect, `isatty() is False`):
  Append `  →  obsidian://open?vault=<name>&file=<path>` as plain text after the snippet.
  If `obsidian_url` is None → nothing appended.
- **SKILL.md update**: JSON schema section lists the two new fields; markdown-format section
  documents OSC 8 behaviour + TTY/non-TTY distinction; Obsidian URI format and vault-name
  derivation are explained.
- **Tests** (see §5):
  - `test_search_json_includes_file_path_and_obsidian_url` — vault known → both fields populated.
  - `test_search_json_obsidian_url_null_when_vault_unknown` — `repo.get_vault` returns None → field is null.
  - `test_search_json_vault_cache_called_once_per_unique_vault` — two hits for the same vault → `get_vault` called exactly once.
  - `test_search_markdown_tty_osc8_link` — stdout patched as TTY → OSC 8 escape present in output.
  - `test_search_markdown_pipe_plain_url` — stdout not TTY → plain URL appended, no ANSI escapes.

### Out of scope (explicit non-goals)
- A `--no-obsidian-links` flag or any opt-out mechanism (links are always-on in both formats
  when vault name is resolvable; consumers that don't need the URL simply ignore the JSON field).
- The `obsidian://new`, `obsidian://search`, or any other Obsidian URI action — only `open`.
- Stripping the `.md` extension from the `file_path` in the URL (Obsidian accepts both; keeping
  the extension avoids ambiguity and matches `Page.file_path` exactly).
- Any change to exit codes, the error envelope schema, or non-search CLIs.
- Any change to the SQLite schema, FTS behaviour, or indexing pipeline.
- Any new Python runtime dependencies (`urllib.parse` is stdlib).
- Changing the `--format` choices or introducing a new format.
- Opening Obsidian automatically from the CLI (the URI is clickable — the user clicks).

---

## 3. Requirements (RTM)

| ID | Requirement | MVP? | Sub-features |
|----|-------------|------|--------------|
| **R-1** | **`file_path` in JSON hits** — every hit in the `hits[]` array includes `file_path: str` (the `Page.file_path` value, relative to vault root). | ✅ | (a) Field is always present — never null, never omitted; (b) value is `h.page.file_path` verbatim (the Class B mirror of the actual path); (c) no modification (no path-join, no absolute, no stripped extension). |
| **R-2** | **`obsidian_url` in JSON hits** — every hit includes `obsidian_url: str | null`. | ✅ | (a) Value is `"obsidian://open?vault=<vault_name>&file=<encoded_path>"` when vault is resolvable; (b) `vault_name` = `vault.root_path.name` (basename only, not full path); (c) `<encoded_path>` = `urllib.parse.quote(h.page.file_path, safe='/-_.~')`; (d) `null` (JSON `null`) when `repo.get_vault(h.page.vault_id)` returns None; (e) `null` when `h.page.vault_id == GLOBAL_VAULT_SENTINEL` (belt-and-braces, sentinel rows should not appear in hits but may if DB is inconsistent). |
| **R-3** | **Vault lookup cache** — `repo.get_vault()` is called at most once per unique `vault_id` in the result set, not once per hit. | ✅ | (a) Build `vault_cache: dict[str, Vault | None]` by iterating `{h.page.vault_id for h in hits}` before serialising; (b) populate with `repo.get_vault(vault_id)` for each unique id; (c) hits then index into cache — no second DB call per hit; (d) a vault not found in the registry maps to `None` in cache (not an error). |
| **R-4** | **Markdown format — TTY branch** — when `sys.stdout.isatty()` is True AND `obsidian_url` is available, an ANSI OSC 8 clickable link is APPENDED after the snippet (same line). | ✅ | (a) OSC 8 escape sequence appended at line end: `  →  \033]8;;<obsidian_url>\033\\[↗]\033]8;;\033\\`; (b) the existing wikilink syntax (`[[vault:project/slug\|title]]`), BM25 score, and snippet are all unchanged — the OSC 8 is purely additive at the end of the line; (c) if `obsidian_url` is None for a hit → nothing appended, line unchanged; (d) the OSC 8 sequence MUST terminate with `\033]8;;\033\\` to prevent the link from bleeding into subsequent terminal output. |
| **R-5** | **Markdown format — non-TTY branch** — when `sys.stdout.isatty()` is False AND `obsidian_url` is available, the plain URL is appended after the snippet. | ✅ | (a) Format: `(BM25=<score>) — "<snippet>"  →  <obsidian_url>` (two spaces before `→`); (b) if `obsidian_url` is None → nothing appended (line ends at snippet, same as today); (c) no ANSI escape sequences emitted when not TTY (clean pipe output). |
| **R-6** | **URL encoding** — `file_path` is percent-encoded in the `obsidian_url` using `urllib.parse.quote`. | ✅ | (a) `safe='/-_.~'` — keep forward slashes, hyphens, underscores, dots, tildes unencoded; (b) spaces, Cyrillic, CJK, brackets and other non-ASCII / special chars are percent-encoded; (c) the vault name (basename) is also percent-encoded via the same function before interpolation; (d) no double-encoding (quote is applied once, not to an already-quoted string). |
| **R-7** | **SKILL.md update** — `skills/wiki-search/SKILL.md` documents the two new JSON fields and the markdown-format link behaviour. | ✅ | (a) JSON schema section adds `file_path` and `obsidian_url` with types and null condition; (b) markdown-format section explains OSC 8 branch (TTY) vs plain-URL branch (pipe); (c) vault-name derivation (folder basename) explained; (d) note that `obsidian_url` is null if the vault is not in the registry. |
| **R-8** | **Tests green** — new unit tests pass; no pre-existing test regressions. | ✅ | See §5 for the 5 test scenarios. |
| **R-9** | **`mypy --strict scripts/` clean** — new code is fully type-annotated; `urllib.parse.quote` return type is `str`; `vault_cache` typed as `dict[str, Vault \| None]`; `obsidian_url` typed as `str \| None`. | ✅ | (a) Import `from urllib.parse import quote as _url_quote` at top of `wiki_search.py`; (b) import `Vault` from `scripts.wiki_index.models` (already imported via `PageHit` — check if `Vault` needs a direct import); (c) no `# type: ignore` added. |
| **R-10** | **No breaking change** — existing JSON consumers are unaffected. | ✅ | (a) No existing key is removed or renamed; (b) no existing key changes type; (c) the two new keys (`file_path`, `obsidian_url`) are purely additive; (d) `pytest tests/` green (all pre-existing tests pass). |
| **NF-1** | **Vendor-agnostic** — `urllib.parse` is stdlib; no anthropic SDK, no vendor-specific tool. | ✅ | (a) No `import anthropic`; (b) no subprocess; (c) `sys.stdout.isatty()` is stdlib. |
| **NF-2** | **Security** — URL is data-only (H-6 safe), OSC 8 sequence is bounded. | ✅ | (a) Vault name and file path come from the Class B DB (already sanitised by the ingest path); (b) the URL is constructed from controlled inputs, not operator/user-supplied freeform text; (c) the OSC 8 sequence terminates with `\033]8;;\033\\` so a malformed URL cannot bleed into subsequent terminal output; (d) no shell expansion — the URL is passed to the terminal as an escape sequence, not evaluated. |

---

## 4. Use cases

- **UC-1 (Standard JSON search, vault known).**
  `wiki-search "machine learning"` → exit 0, JSON envelope; each hit in `hits[]` now has:
  ```json
  {
    "vault_id": "personal",
    "slug": "machine-learning",
    "file_path": "_concepts/machine-learning.md",
    "obsidian_url": "obsidian://open?vault=MyVault&file=_concepts/machine-learning.md",
    ...
  }
  ```
  Operator copies `obsidian_url` or uses `file_path` for a `Read` call.

- **UC-2 (Multi-vault search — `--vaults all`).**
  Results span two vaults: `personal` and `work`. The vault cache resolves both with a
  single `get_vault` call each. Hits from `personal` carry that vault's name in the URL;
  hits from `work` carry the other vault's name. No cross-contamination.

- **UC-3 (Vault not in registry — stale DB).**
  A hit's `vault_id` is `old-vault` but `repo.get_vault("old-vault")` returns `None`.
  Result: `file_path` is populated (it comes from the `pages` row directly), `obsidian_url`
  is `null`. The operator still has `file_path` for reference.

- **UC-4 (`--format markdown` + TTY — clickable links in iTerm2/VS Code terminal).**
  ```
  ## "machine learning" — 3 hits

  - [[personal:_vault_/machine-learning|Machine Learning]] (BM25=-3.21) — "...snippet..."  →  [↗]
  ```
  Where `[↗]` is the OSC 8 ANSI hyperlink (rendered as a clickable arrow in the terminal).
  Clicking it opens the page directly in Obsidian.

- **UC-5 (`--format markdown` + pipe — plain URL in non-interactive context).**
  `wiki-search "machine learning" --format markdown | tee results.txt` →
  ```
  - [[personal:_vault_/machine-learning|Machine Learning]] (BM25=-3.21) — "...snippet..."  →  obsidian://open?vault=MyVault&file=_concepts/machine-learning.md
  ```
  No ANSI escape sequences; plain text is grep-able and copy-pasteable.

- **UC-6 (Path with Cyrillic/spaces — correct URL encoding).**
  `file_path = "Lessons/Моя лекция/concept.md"` →
  `obsidian_url = "obsidian://open?vault=MyVault&file=Lessons/%D0%9C%D0%BE%D1%8F%20%D0%BB%D0%B5%D0%BA%D1%86%D0%B8%D1%8F/concept.md"`
  Obsidian handles percent-encoded UTF-8 paths correctly.

- **UC-7 (NEG — no change to error envelopes).**
  Invalid queries, filter errors, and empty result sets are unaffected — they never reach
  the results-serialisation code path.

---

## 5. Acceptance / definition of done

1. **`pytest tests/` green** (all pre-existing tests pass; 5 new test scenarios pass):
   - `test_search_json_includes_file_path_and_obsidian_url`: mock repo returns a hit with
     a known vault (root_path=`/Vaults/MyVault`) and `file_path="_concepts/foo.md"` →
     JSON output includes `file_path="_concepts/foo.md"` and
     `obsidian_url="obsidian://open?vault=MyVault&file=_concepts%2Ffoo.md"`.
   - `test_search_json_obsidian_url_null_when_vault_unknown`: `repo.get_vault` returns
     `None` → JSON hit has `obsidian_url=null`.
   - `test_search_json_vault_cache_called_once_per_unique_vault`: two hits for `vault_id="v1"`,
     one for `"v2"` → `repo.get_vault` called exactly 2 times, not 3.
   - `test_search_markdown_tty_osc8_link`: patch `sys.stdout.isatty` → `True`;
     run `main(["query", "--format", "markdown"])` with a mock repo → stdout contains
     `\033]8;;obsidian://` AND `\033]8;;\033\\` (the closing terminator) substrings.
   - `test_search_markdown_pipe_plain_url`: patch `sys.stdout.isatty` → `False`;
     run `main(["query", "--format", "markdown"])` → stdout contains literal
     `obsidian://open?vault=` substring but NO `\033]8;;` ANSI sequence.

2. **`mypy --strict scripts/` clean** on all modified files.

3. **No `import anthropic`** in any new or modified file (grep gate).

4. **`skills/wiki-search/SKILL.md`** updated per R-7.

5. **Additive-only JSON change**: a diff of JSON outputs before vs after shows only the
   addition of `file_path` and `obsidian_url` keys to each hit — no removed/renamed keys.

6. **VDD reviewers APPROVE**: `code-reviewer` (correctness, R-10 non-regression proof, URL
   encoding, vault cache logic) + `critic-logic` (null-safety, multi-vault correctness,
   `isatty` TTY/non-TTY branching, OSC 8 sequence terminator).

---

## 6. Risks / open questions

- **Q-045-1 (OSC 8 + Obsidian URI in Wikilink syntax).** The markdown format wraps the OSC 8
  sequence INSIDE a Wikilink (`[[...|<osc8>]]`). Whether the OS terminal renders the link
  correctly when the OSC sequence is embedded inside brackets depends on the terminal emulator.
  If rendering is broken, the fallback (non-TTY plain URL) is always available via piping.
  Mitigation: the test verifies the escape is present; manual dogfood in iTerm2 confirms.

- **Q-045-2 (Vault name vs vault_id).** Obsidian identifies vaults by their root folder name
  (`vault.root_path.name`), NOT the registry `vault_id`. These are the same for most vaults
  but could differ if the user renamed the folder. In that case `obsidian://open?vault=...`
  will fail silently in Obsidian (vault not found). This is a user-configuration issue, not
  a bug in this feature — document in SKILL.md.

- **Q-045-3 (`safe` chars in `urllib.parse.quote`).** Using `safe='/-_.~'` keeps slashes
  unencoded, which is correct for the `file` parameter of the Obsidian URI (Obsidian accepts
  slash-separated paths). Alternative: encode everything including slashes — Obsidian handles
  both. The more readable form (slashes unencoded) is chosen; encoded slashes are only needed
  if the vault path itself contains literal `%2F` sequences (extremely unlikely).
