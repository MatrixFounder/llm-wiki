---
id: DF-074-2
type: known-issue
status: fixed
opened_at: 2026-08-10
fixed_at: 2026-08-10
category: security
severity: SEV-3
slug: df-074-2-tsv-emitters-do-not-escape-tabs-and-newlines
---

# Two of the three `--format tsv` emitters don't escape tabs/newlines — the third added `_clean()` for exactly that reason and the fix was never carried across

- **Symptom**: `obsidian_context.py:209-213` carries a `_clean()` helper with an explicit
  rationale — «escape embedded tabs/newlines in untrusted author-controlled fields so a crafted
  heading/tag cannot break the row structure of a downstream parser». Its two siblings emit raw:

  - `skills/obsidian-cli/scripts/obsidian_selection.py:619-626` — `"\t".join(str(item.get(k, "")) …)`
    over `path` and `reason`, both plugin-supplied;
  - `skills/obsidian-cli/scripts/obsidian_active_note.py:448` — the same unescaped join.

  A `path` containing a tab forges columns; one containing a newline forges rows. On macOS a
  filename may legally contain both.

- **Why it matters at all**: `--format tsv` exists so a *shell* consumer can `cut -f`. A forged
  row is a value the consumer attributes to the wrong field — the classic CWE-117 output-encoding
  bug, in the one output mode that has no structural framing to fall back on. (The JSON path is
  unaffected: `json.dumps` escapes both.)

- **Severity SEV-3**: needs an attacker-controlled filename or a hostile `agent-result.json`, and
  the blast radius is a mis-parsed shell pipeline rather than code execution.

- **Fix shape** (not done here): lift `_clean` out of `obsidian_context.py` into the module the
  three wrappers share and call it in all three emitters. One helper, three call sites; the
  rationale comment is already written.

- **Found by**: `critic-security` during the `/vdd-multi` pass on TASK 074 (F5). Out of that
  task's diff. Same provenance as [[df-074-1-obsidian-wrappers-echo-an-unallowlisted-plugin-reason]]:
  the reviewer was pointed at the `obsidian-*` trio *because* TASK 074's new gate pins them as a
  static blind spot.

---

## Resolution — TASK 074 (same session), 2026-08-10

**Fixed at all three sites.** The local closure in `obsidian_context.py` is hoisted to
`obsidian_selection.tsv_field()` (and now also neutralises `\r`, which the original missed).
`obsidian_context.py` binds `_clean = _sel.tsv_field`; `obsidian_selection._emit` and
`obsidian_active_note._emit` call it on every column.

`obsidian_active_note.py` had **no** cross-import before this, so it gained the same
`sys.path`-insert + `import obsidian_selection as _sel` block `obsidian_context.py` already uses —
stdlib-only, so its "runs under any python3, no repo venv" property is preserved. The alternative
(a third local copy) is exactly the re-port this project banned after TASK 071's 3-critic FAIL.

Pinned by `test_tsv_field_neutralises_the_row_and_column_separators` (unit: tab, newline, CRLF,
non-str) and `test_apply_format_tsv_cannot_be_row_forged_by_a_crafted_path` (the guard at its real
call site: a `path` carrying both a tab and a newline yields one row and one column).
