---
id: DF-074-3
type: known-issue
status: fixed
opened_at: 2026-08-10
fixed_at: 2026-08-10
category: logic
severity: SEV-4
slug: df-074-3-validate-vault-id-accepts-the-global-sentinel
---

# `wiki-init` accepts `_global_` as a real `vault_id` — the value `layout.py` reserves to mean "no specific vault"

- **Symptom**: `scripts/wiki_skills/wiki_init.py:_validate_vault_id` short-circuits to `True` for
  the literal `_global_`, while `scripts/wiki_index/layout.py` defines
  `GLOBAL_VAULT_SENTINEL = "_global_"` — the value used to mean *cross-vault / not a specific
  vault*. So `wiki-init --scaffold-new --vault X --vault-id _global_` registers a real vault under
  the sentinel.

  Note it also bypasses the pattern the refusal envelope advertises: `_global_` matches neither
  `^[a-z][a-z0-9-]{1,30}[a-z0-9]$` (underscores) nor the `"--" not in vault_id` rule that the
  emitted `pattern` key likewise does not express.

- **Why SEV-4 and not higher**: whether a collision is *reachable* was not traced. The carve-out
  is presumably deliberate (something needs to register the global partition), but it is
  undocumented at the site, so "deliberate" is an inference rather than a fact. No live vault uses
  it. Filing it so the next reader does not have to re-derive the same uncertainty.

- **Fix shape** (not done here): decide and state which it is —
  1. **Deliberate**: comment the carve-out at `_validate_vault_id`, name it in
     `skills/wiki-init/SKILL.md`, and add a test pinning that `_global_` is accepted *on purpose*;
     or
  2. **Not deliberate**: refuse it in the operator-facing paths (`--vault-id`, `WIKI_SCHEMA.md`
     frontmatter) and keep the exemption internal to whatever registers the global partition.

  Either way, `_validate_vault_id`'s advertised `pattern` should stop being the whole story in the
  envelope — an operator who satisfies `pattern` with `a--b` gets the same refusal and no new
  information (a separate nit from the same review).

- **Found by**: `critic-security` during the `/vdd-multi` pass on TASK 074 (F8), while auditing
  the three `INVALID_VAULT_ID` envelopes that task rewrote. Pre-existing; outside that diff.

---

## Resolution — TASK 074 (same session), 2026-08-10 — **option 1: it is deliberate**

**Traced, and the issue's own lean toward option 2 was wrong.** `_global_` is load-bearing:

- it is `layout.GLOBAL_VAULT_SENTINEL`, the vault_id `wiki-search --log-access` attributes a
  **multi-vault** read to (`wiki_search.py:214,307,331`) — charging it to one named vault would be
  a false attribution;
- `repository.list_vaults` / `_vaults.py:65` explicitly **exclude** it from "all registered
  vaults", i.e. the schema already treats it as a real-but-hidden row;
- `wiki-init` is the **only** surface that calls `register_vault`, so refusing `_global_` on the
  operator paths would make that row **unseedable** and multi-vault read-audit permanently
  unattributable. `tests/test_read_access_logging.py:150` already documents the fail-soft that
  results when the row is absent.

So: **documented, not refused.** The carve-out now carries its reason at
`_validate_vault_id`, a section in `skills/wiki-init/SKILL.md`, and
`test_global_sentinel_is_an_accepted_vault_id_on_purpose` — which also asserts the id genuinely
does **not** match `_VAULT_ID_RE`, so the exception cannot be quietly "simplified" away.

**The sub-nit is fixed too.** «the caller loses nothing» (the DF-072-5 rationale) was overstated:
`_validate_vault_id` enforces two rules the emitted `pattern` cannot express, so an operator
satisfying the regex with `a--b` got an identical refusal carrying no new information. All three
`INVALID_VAULT_ID` envelopes now carry a `constraints` list naming both rules, plus a `source` key
distinguishing «your `--vault-id` is bad» from «the id derived from your folder name is bad» —
the discriminator the removed `received` used to provide. Both are repo constants: no operator
value is echoed.
