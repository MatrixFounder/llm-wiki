---
id: DF-072-8
type: known-issue
status: partially-fixed
opened_at: 2026-08-07
resolved_at: 2026-08-07
category: correctness
severity: SEV-2
slug: df-072-8-live-dbs-frozen-at-schema-v5-undetected
---

# The global index DB was frozen at **schema v5** while the repo ships v7 — every event-graph typed edge was UNWRITABLE there, and **nothing in `scripts/` reads `PRAGMA user_version`**, so nothing detected it

> ## ✅ REBUILT 2026-08-07 (operator-authorised) — and one claim of this issue CORRECTED
>
> `global.db` was rebuilt per the documented Class-B procedure. **The rebuild is exact**:
> `user_version` 5 → **7**, pages **613 → 613**, refs **3933 → 3933**, `PRAGMA
> integrity_check` ok. Nothing was lost, because nothing was ever DB-only — ADR-002 §D8
> proving itself on a real 613-page vault rather than in a test. The reproducer below now
> INVERTS: all **7/7** forward typed edges insert cleanly on a copy of the rebuilt DB.
> The two dead registrations (`audit-scaffold-personal`, `karptest` — both
> `/private/tmp/...` roots long gone) were dropped, as intended.
>
> ⚠️ **CORRECTION to this issue's own headline.** It said "*both live index DBs*", which
> over-generalised from the two DBs that were checked. The vault-local DB at
> `Downloads/TestVault/ObsidianNotes-Test/.wiki/index.db` was **already v7** with the full
> 14-edge CHECK. The real pattern is AGE, not "DBs in general": `global.db` was created
> 2026-06 and never rebuilt across two schema bumps; DBs created later are correct.
>
> **STILL OPEN — the part that actually matters.** The absence of detection is unchanged:
> `grep -rn user_version scripts/` still returns comments only. A DB left behind by the
> next schema bump will fail exactly the same way, silently. This issue stays
> `partially-fixed` for that reason: the instance is repaired, the class is not.

Found by running TASK 072's own final gate (`PRAGMA user_version == 7`) instead of ticking
it. The schema FILE is correct — `sql/wiki-index-v2.sql:481` is `PRAGMA user_version = 7;`.
The DBs on disk are not.

```
$ sqlite3 .wiki/index.db                                   'PRAGMA user_version;'   → 5
$ sqlite3 ~/Library/…/wiki-index/global.db                  'PRAGMA user_version;'   → 5
```

## It is not a cosmetic marker — the CHECK constraint is v5 too

```
$ sqlite3 <global.db> "SELECT sql FROM sqlite_master WHERE name='page_entity_refs';"
    ref_type TEXT NOT NULL CHECK (ref_type IN (
        'mentioned', 'defined-here', 'related', 'cited',
        'verifies'   -- TASK 008 / R-8.9 (schema v5)
    )),
```

**All 14 event-graph edges are missing**: the v6 pairs (`implements`/`implemented-by`,
`supersedes`/`superseded-by`, `causes`/`caused-by`) and the v7 pairs (`invalidated-by`/
`invalidates`, `activated-by`/`activates`, `uses`/`used-by`, `owns`/`owned-by`).

Proved by execution, **on a COPY — never on the operator's DB**:

```
$ cp <global.db> /tmp/probe.db
$ sqlite3 /tmp/probe.db "INSERT INTO page_entity_refs
    (vault_id,page_slug,page_project,entity_slug,ref_type)
    VALUES ('obsidian-llm-wiki','x','_vault_','y','implements');"
Error: stepping, CHECK constraint failed: ref_type IN ('mentioned','defined-here',
       'related','cited','verifies' …)
```

## What is therefore non-functional on these DBs

Everything downstream of ADR-003/004 typed knowledge: `wiki-graph` typed traversal,
`wiki-search --as-of` (it walks the supersede/invalidate graph), and the
`wiki-extract-decisions` rail's forward-edge writes. Not degraded — **refused at the
storage layer**.

Nothing has surfaced because the only vault regularly reindexed here (`docs/`,
dev-project layout) produces `mentioned`/`related` refs, which are v5-legal.

## The actual defect is the ABSENCE OF DETECTION

`grep -rn user_version scripts/` returns **only comments and docstrings — zero reads.**
The durable invariant says a vN→vN+1 bump is a Class-B rebuild, never an in-place ALTER;
what it does not say, and what no code enforces, is that a DB left at the old version is
**detected**. So this failed open for two schema generations. A gate nobody runs and code
that never checks is the same thing as no gate.

## Remedy — operator's call, NOT run here

The documented Class-B rebuild (the DB is 100% rebuildable from markdown by ADR-002 §D8):

```bash
rm ~/Library/Application\ Support/wiki-index/global.db*
wiki-init --register-existing --vault <id> --vault-root <path>   # per vault
wiki-reindex --full --vault <id> --vault-root <path>
```

⚠️ **Not run by the agent.** `global.db` currently registers three vaults, two of whose
roots are `/private/tmp/...` paths that no longer exist — a rebuild silently drops those
registrations, and deciding that is the operator's, not the agent's.

The repo-local `.wiki/index.db` is a separate matter: last written **2026-07-15**, and the
`docs/` vault does not declare `index_db:`, so it resolves to the GLOBAL db — that file is
stale and unused. `CLAUDE.md` already warns against rendering ledgers off it.

## Residual — deliberately not fixed in 072-11

Adding a `PRAGMA user_version` check to `SQLiteRepositoryBase` is a behaviour change on a
shipped DAL that would refuse on every existing install, and it needs a decision about
refuse-vs-warn. Its own task. What 072-11 does is make the finding exist.

## Related

- [[the-unenumerated-surface-lens]] — a gate stated in a plan and never executed.
- ADR-002 §D8 — Class B rebuildability is what makes the remedy safe.
- `sql/wiki-index-v2.sql:481` — the declared version, which is correct.
