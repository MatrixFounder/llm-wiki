# obsidian-cli eval fixtures — provenance

Real captured output from the live `obsidian` CLI, used by `tests/test_obsidian_active_note.py`
(deterministic, no live app needed) and as the byte-anchor for the command-reference.

| Fixture | Command | Notes |
|---|---|---|
| `obsidian-help-1.12.7.txt` | `obsidian help` | full command surface (TASK 029) |
| `obsidian-commands-1.12.7.txt` | `obsidian commands` | (TASK 029) |
| `obsidian-file-active.tsv` | `obsidian file path=README.md` | active-file info FORMAT (TASK 041 S0) |
| `obsidian-file-no-active.txt` | `obsidian file` (nothing open) | the `No active file` error (TASK 041 S0) |
| `obsidian-file-not-found.txt` | `obsidian file file=NoSuchNoteXYZ123` | the `Error: File "X" not found.` message, rc=0 (TASK 041 S8 / F-4) |
| `obsidian-files-md.txt` | `obsidian files ext=md` (trimmed sample) | basename-uniqueness input for the F-1 guard — a curated 8-line sample incl. a duplicate `GitHub Setup` (TASK 041 S8 / F-1) |
| `obsidian-tabs.txt` | `obsidian tabs` | open tabs: `[view-type] Title` (TASK 041 S0) |
| `obsidian-tabs-ids.txt` | `obsidian tabs ids` | `[view-type] Title\t<id>` (TASK 041 S0) |
| `obsidian-recents.txt` | `obsidian recents` | recently-opened vault-relative PATHS (TASK 041 S0) |
| `obsidian-vaults-verbose.tsv` | `obsidian vaults verbose` | `name\tpath` per vault (TASK 041 S0) |
| `obsidian-tabs-with-base.txt` | `obsidian tabs` (a Base focused, no markdown open) | `[bases] Title` — the live-verified view-type for an open Obsidian Base (TASK 060) |
| `obsidian-file-base.tsv` | `obsidian file path=<a .base file>` | a `.base` file's `file` info TSV — same shape as markdown, `extension\tbase` (TASK 060) |

**Provenance (TASK 041 S0 captures):** `obsidian 1.12.7 (installer 1.12.7)`, macOS (Darwin),
captured 2026-06-20 against the registered `obsidian-llm-wiki` vault (the active vault at capture
time had no markdown note open — hence the `No active file` capture; `obsidian-file-active.tsv` was
taken with an explicit `path=` to pin the identical output FORMAT).

**Provenance (TASK 060, `.base` fixtures):** `obsidian 1.12.7`, macOS, captured 2026-07-11 against a
real vault with an Obsidian Base file open and focused. Confirms: (a) `tabs` reports a Base tab as
`[bases] <Title>` (no extension in the title, same as markdown); (b) `obsidian file` (bare, no
`path=`/`file=`) still returns `Error: No active file` even though the Base is the genuinely-focused
leaf — Obsidian's own active-file pointer doesn't recognize a Bases view, which is exactly why the
`recent-open` fallback (not the primary `active` path) is how a focused Base ever resolves; (c)
`obsidian file path=<x>.base` returns the same TSV shape as a markdown file (`extension\tbase`); (d)
`obsidian file file=<title-without-extension>` — the wikilink-style resolve `match`/`resolve_title`
depend on — does **NOT** find a `.base` file by bare title (`Error: File "X" not found.`); it only
resolves when the extension is appended (`file=<title>.base`). (d) is why the descriptor `match` HIGH
path stays markdown-only (see `markdown_tabs` docstring) rather than being widened alongside
`open_file_tabs`.

## TASK 041 S0 capability decision (the entry gate)

What the live CLI actually exposes (Q-041-1 / arch-review M-1/M-2 — RESOLVED against these fixtures):

- **`obsidian file` (no `path=`) → active-file resolver — WORKS.** Output is TSV
  `path\t<vault-rel>\nname\t…\nextension\t…\n…`; `format=json` is **ignored** (same TSV). With no
  note open it prints `Error: No active file. Use file=<name> or path=<path> to specify a file.`
  → **MEDIUM (bare-ref → focused tab) is fully feasible** (parse line `path\t<X>`; the error is the
  `NO_ACTIVE_FILE` signal). **M-2 RESOLVED: the active-file path IS recoverable.**
- **`obsidian tabs` → open-tab enumeration by TITLE only.** `[view-type] Title` (`ids` appends
  `\t<id>`). **No path field, no focus marker.** So open-tab→path is a **two-step** composition:
  match the descriptor to a unique `[markdown] <Title>`, then `obsidian file file="<Title>"` →
  `path\t<X>` (wikilink-style resolve).
- **`obsidian recents` → vault-relative PATHS, most-recent first** — a recency heuristic over the
  vault, NOT the open-tab set (N1).
- **`obsidian vaults verbose` → `name\tpath`** per vault — the `vault-mismatch` / vault-identity source.

**Decision (per the PLAN S0 contingency): TEMPERED HIGH.** The descriptor branch keeps the user's
**no-ask** path — but ONLY when the descriptor matches **exactly ONE open `[markdown]` tab AND** the
title `file=`-resolves to a **basename that is unique in the vault** (`obsidian files ext=md`).
`obsidian file file=<title>` resolves wikilink-style *vault-globally* (NOT pinned to the open tab),
so a duplicate basename (which exists in real vaults — e.g. multiple `README.md`/`CLAUDE.md`) means
the resolve can't be proven to be the open tab → it **degrades to LOW → ASK** (the `match` mode
returns exit 7 AMBIGUOUS). This double guard (unique-open-tab + vault-unique-basename) is the F-1
fix; it satisfies arch-review M-1 (the candidate set is enumerated, with a hard ambiguity guard).
Bare-ref stays **MEDIUM** (confirm-first-per-session). Narrower than full no-ask, broader than the
contingency's confirmed-MEDIUM — it best honors the user's explicit request while staying safe.
