# PLAN — TASK 018 `wiki-sync` (R-11)

Stub-First, **green-throughout**. **17 beads** (018-00…16). **Zero DDL** (`user_version`
stays **5**; new `source_state` `source_kind='sync'` partition is data). `mypy --strict
scripts/` + full `pytest` green at **every** bead. `wiki-sync` carries **no `import
anthropic`** (Decision-17). Built-in-layout byte-identity untouched.

Design is **locked** across two adversarial gates (`docs/reviews/adversarial-018-review.md`
+ `architecture-018-rereview.md`): [docs/TASK.md](docs/TASK.md) (RTM E1–E4 + AC-1..14) and
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) §11a **Q-018-1..10** + functional-architecture.md
*Sync Dispatcher* + interfaces §5.4 + security §7.5 + data-model *SourceState partition*.

> **`skill-tdd-strict` for the correctness/security-critical beads (PR-1).** Beads **02**
> (idempotency: re-run no-op + zero-DDL), **04** (YAML anchor-bomb — RED must demonstrate the
> bomb is *refused*, i.e. expands/DoSes without the anchor-ban guard), and **14** (the H-6 fence
> before `summarizing-meetings`) follow strict RED-first TDD. All other beads follow Stub-First
> green-throughout.

## Shape (Decision-17, locked)

- **`wiki-sync scan <zone>`** — deterministic, plan-only CLI (`scripts/wiki_skills/wiki_sync.py`):
  own walk → classify → strict **plan JSON** (no LLM/network/mutation). Beads 01–13.
- **`workflows/wiki-sync.md`** — orchestrator executor (convert / de-timestamp / H-6-fence /
  summarise / enrich / extract / upsert / skip; per-vault `flock`; commit-marker). Bead 14.
- Idempotency = a **`wiki-sync`-owned `source_state` partition** (`source_kind='sync'`,
  scope=vault-rel path, `key='source_hash'`, value=`sha256(file bytes)`), read by scan,
  written by the executor on success (Q-018-8). Two new generic zero-DDL DAL methods.
- Conversion → harness `docx`/`pdf`/`pptx`/`xlsx` skills; `.vtt`/`.srt` de-timestamp →
  transcript-fetcher `_vtt_to_text.py`; staged output → **non-walked `_raw/.staging/`** (Q-018-3).

## Phases

- **Phase 0 — anchor** (bead 00): no-regression baseline + new test module.
- **Phase 1 — DAL + config** (01–04): `get/set_source_state` (zero-DDL); `.wiki/sync.yaml`
  loader (256 KiB cap + anchor-ban `SafeLoader` + strict `config/sync-config.schema.yaml`).
- **Phase 2 — classifier** (05–09): extension routing (case-fold), tag vocab + precedence,
  generated-view detection + only-a-view guard, unmappable-type predictor (layout-general) +
  degenerate inputs.
- **Phase 3 — walk + scan CLI** (10–13): own bounded walk (single-stat, `.staging/`+`exclude:`
  pruning, `#wiki/keep` read), `wiki-sync scan` plan-emit + `--dry-run` + envelopes/exit codes.
- **Phase 4 — executor + surface** (14): `workflows/wiki-sync.md` + `skills/wiki-sync/SKILL.md` +
  `bin/wiki-sync` + `commands/wiki-sync.md` + symlinks.
- **Phase 5 — acceptance** (15): e2e fixtures (incl. the operator's real `yaml:dbfolder`) +
  AC-1..14 (idempotency / convert-convergence / determinism / dry-run).
- **Phase 6 — close** (16): README/.AGENTS.md/ROADMAP R-11→shipped/CLAUDE/KNOWN_ISSUES residual.

## Beads

| # | Bead | Phase | Files | Stub-First RED → GREEN | RTM |
|---|------|-------|-------|------------------------|-----|
| **018-00** | Anchor + test module | 0 | `tests/test_wiki_sync.py` (new) | Baseline `pytest -q` + `mypy --strict` green; 1 smoke test (module-import placeholder for `scripts.wiki_skills.wiki_sync` once 12 lands — assert the test file collects). | AC-9 baseline |
| **018-01** | [STUB] DAL `get/set_source_state` | 1 | `scripts/wiki_index/repository.py`, `scripts/wiki_index/sqlite_repository.py`, `tests/…` | Add ABC signatures `get_source_state(vault_id,source_kind,scope,key)->str\|None` + `set_source_state(...,value)->None`; `SQLiteRepository` stubs `raise NotImplementedError`. RED `test_source_state_roundtrip`. | E3.4d, Q-018-8 |
| **018-02** | [LOGIC] DAL impl + zero-DDL | 1 | `scripts/wiki_index/sqlite_repository.py`, `tests/…` | `set_source_state` = `INSERT … ON CONFLICT(vault_id,source_kind,scope,key) DO UPDATE`; `get_source_state` = SELECT. GREEN round-trip + `test_source_state_zero_ddl` (`user_version==5`; `'sync'` kind accepted — no CHECK). | E3.4d, Q-018-8, AC-8 |
| **018-03** | [STUB] sync-config schema + loader | 1 | `config/sync-config.schema.yaml` (new), `scripts/wiki_index/sync_config.py` (new), `tests/…` | Author the strict schema (`zones`,`exclude`,`tag_namespace`,`extensions`; `additionalProperties:false`); `load_sync_config(vault_root)->SyncConfig` stub returns defaults; anchor-ban `SafeLoader` subclass stub. RED: misspelled-key → error; anchor → error; >256 KiB → error. | E4.1, Q-018-4, META-4 |
| **018-04** | [LOGIC] sync-config loader | 1 | `scripts/wiki_index/sync_config.py`, `tests/…` | `stat().st_size` ≤256 KiB gate; custom `SafeLoader` that **raises on anchor/alias** (SEC-N3 — `safe_load` alone expands them); jsonschema strict-validate; pin `exclude`×`keep` precedence. GREEN: valid config; misspelled→`INVALID_SYNC_CONFIG` exit 6; 232-byte anchor-bomb refused; size-cap. | E4.1, SEC-A5/N3, META-4 |
| **018-05** | [STUB] classifier surface | 2 | `scripts/wiki_skills/_sync.py` (new), `tests/…` | `Decision` dataclass (`action`,`reason`,`converter`,`staged_target`,`normalize`); `classify_file(path, *, vault_root, config, layout, in_raw, in_exclude_zone) -> Decision` stub returns `skip`. RED matrix (one case per route). | E1, E2 |
| **018-06** | [LOGIC] extension routing | 2 | `scripts/wiki_skills/_sync.py`, `tests/…` | `ext = path.suffix.lower()`; convert(`.docx/.xlsx/.pptx/.pdf`) / text(`.txt/.vtt/.srt`) / md / binary-skip; `.excalidraw.md`/`.canvas`→skip; unknown→`skip:unknown-ext`. GREEN AC-3 + EC-6. | E1.1/1.2, AC-3 |
| **018-07** | [LOGIC] tag vocab + precedence | 2 | `scripts/wiki_skills/_sync.py`, `tests/…` | Parse `#wiki/{raw,skip,keep}` (tags) + `wiki:` field; `_raw/`≡raw; precedence **skip>raw>keep>default**; `#wiki/keep` rescues an `exclude:`-zone `.md`. GREEN AC-4 + Q-018-7. | E2.1/2.3, AC-4 |
| **018-08** | [LOGIC] view-sidecar + only-a-view | 2 | `scripts/wiki_skills/_sync.py`, `tests/…` | Detect DB Folder (`database-plugin:` / fenced `yaml:dbfolder`), Bases (`base`/`.base`), Dataview (`dataview(js)`), folder-note (stem==dir); **only-a-view ratio** matcher (RC-4: body is essentially one fenced view block, modulo frontmatter) — embedded-view content note NOT skipped (AC-2b). RC-5: decide `_count_md_structure` reuse (documented). GREEN AC-2 + AC-2b. | E2.2, AC-2/2b |
| **018-09** | [LOGIC] unmappable-type + degenerate | 2 | `scripts/wiki_skills/_sync.py`, `tests/…` | No-tag `.md` → `upsert` only if `type:` mappable by the **same `normalize_frontmatter` layout resolution** `wiki-index-upsert` uses (W-1) else `skip:unmappable-type`; empty/zero-byte → `skip:empty-source`; unparseable frontmatter → route-by-path, never raise. GREEN AC-11 + AC-12(part) + EC-2/EC-7. | E2.3, AC-11 |
| **018-10** | [STUB] own walk surface | 3 | `scripts/wiki_skills/_sync.py`, `tests/…` | `iter_sync_candidates(zone, *, vault_root, config) -> list[Candidate]` stub returns `[]`; define the exclusion set (`_raw/.staging/**`, `_raw/.locks`, `_raw/failed`, `config.exclude`). RED `test_walk_discovers_heterogeneous`. | E3.1e, EC-1 |
| **018-11** | [LOGIC] own walk impl | 3 | `scripts/wiki_skills/_sync.py`, `tests/…` | Own walk: free string/glob filter → one `stat()`/candidate → **case-folded** extension prune before any read; prune non-`.md` in `exclude:` immediately but READ `.md` there (for `#wiki/keep`); exclude staged/`.locks`/`failed`; refuse symlinked dirs+targets (`O_NOFOLLOW`). GREEN: discovers `.txt/.vtt/.docx/.pdf/.md`; staged `.md` NOT discovered; one stat/file. | E3.1e, EC-1/ID-5, SEC-A6 |
| **018-12** | [STUB] `wiki-sync scan` CLI + wrappers | 3 | `scripts/wiki_skills/wiki_sync.py` (new), `scripts/wiki_skills/wiki_sync/__main__.py` *(or module)*, `bin/wiki-sync` (new), `commands/wiki-sync.md` (new), `tests/…` | argparse `scan <zone> [--vault] [--vault-root] [--dry-run] [--db-path]`; emit a **hardcoded empty** plan JSON via `_common.emit`; exit 0/2/6; `bin/wiki-sync` wrapper (cd+venv+exec) + slash command. RED e2e `test_scan_emits_plan_envelope`. **No `import anthropic`.** | E3.1, E3.4, AC-9 |
| **018-13** | [LOGIC] scan plan-emit | 3 | `scripts/wiki_skills/wiki_sync.py`, `scripts/wiki_skills/_sync.py`, `tests/…` | Walk→classify each→`source_hash=sha256(bytes)` (original binary for convert)→`is_unchanged` via `get_source_state('sync',rel_path,'source_hash')`; **entries sorted by vault-rel POSIX path**; `summary{}`; `--dry-run` human report (every skip + reason). GREEN AC-1 + AC-10 + AC-13. | E3.1/3.3, AC-1/10/13 |
| **018-14** | Executor workflow + skill + symlinks | 4 | `workflows/wiki-sync.md` (new), `skills/wiki-sync/SKILL.md` (new), `.claude/`+`.agent/` symlinks | Decision-17 recipe per entry: `convert`→harness skill→`_raw/.staging/<slug(stem)>-<ext>.md` (collision-safe, refuse-overwrite-diff, empty-slug fallback SEC-N1); `ingest`→[.vtt/.srt de-timestamp]→**H-6 fence**→`summarizing-meetings`→`wiki-enrich --source <summary>`→`wiki-extract-concepts`; `upsert`→`wiki-index-upsert`; on success `set_source_state('sync',…)` (commit marker); per-vault `flock` `LOCK_NB`→exit 2 `SYNC_IN_PROGRESS`; per-file isolation; `needs-ocr` flagged. SKILL.md = contract + plan JSON + exit codes + triggers. `## Fallback` for non-Claude vendors. | E3.2, Q-018-5, SEC-A1/N4, AC-7 |
| **018-15** | E2E acceptance + fixtures | 5 | `tests/fixtures/sync/**` (new), `tests/test_wiki_sync_e2e.py` (new) | Fixtures: the operator's **real `yaml:dbfolder`** sample + Bases + Dataview + embedded-dataview content note + folder-note + `.vtt` + empty file + a tiny `.docx`/`.pdf` (or a stub converter). Assert the classify matrix (AC-2/2b/3/4), idempotency re-run no-op (AC-5), **convert+ingest convergence** — staged output not re-ingested (AC-14), `--dry-run` writes nothing (AC-6), determinism byte-identical plan (AC-10), degenerate never-raise (AC-11), unmappable/collision (AC-12). | AC-1..14 |
| **018-16** | Docs + close | 6 | `scripts/wiki_skills/.AGENTS.md`, `README.md`, `docs/ROADMAP.md`, `CLAUDE.md`, `docs/KNOWN_ISSUES.md` (+`docs/issues/*`) | README CLI list += `wiki-sync` + Mixed-vault pointer; `.AGENTS.md` entry; **ROADMAP R-11 → SHIPPED**; CLAUDE status; file any residual (none expected — RC-4/RC-5/SEC-N1 closed in beads 08/14) or note as done. Full `pytest` + `mypy --strict` + `wiki-lint` PW-Q clean. | AC-9 docs |

## Dependency / order

```
018-00 (anchor; green throughout)
  → 018-01 [STUB] DAL get/set_source_state
  → 018-02 [LOGIC] DAL impl + zero-DDL            ─┐ Phase 1
  → 018-03 [STUB] sync-config schema + loader      │
  → 018-04 [LOGIC] loader (cap + anchor-ban)      ─┘
  → 018-05 [STUB] classifier surface              ─┐ Phase 2 (06–09 each needs 05)
  → 018-06 [LOGIC] extension routing               │
  → 018-07 [LOGIC] tag vocab + precedence          │
  → 018-08 [LOGIC] view-sidecar + only-a-view      │
  → 018-09 [LOGIC] unmappable-type + degenerate   ─┘  09 needs the layout resolver
  → 018-10 [STUB] own walk surface                ─┐ Phase 3
  → 018-11 [LOGIC] own walk impl (needs 04 config) │
  → 018-12 [STUB] scan CLI + wrappers              │  needs 05 (Decision type)
  → 018-13 [LOGIC] scan plan-emit                 ─┘  needs 02,04,06-09,11
  → 018-14 executor workflow + skill (needs 13 plan contract + 02 set_source_state)
  → 018-15 e2e acceptance + fixtures (needs 13; 14 for the orchestrated AC-5/AC-14 path)
  → 018-16 docs + close
```

## Verification (end-to-end)

> **SHIPPED 2026-06-03** — all 17 beads green; full VDD pipeline + `/vdd-multi`
> 3-critic convergence (Logic ✓ Security ✓ Performance ✓). Final: **986 pytest
> (+4 skipped), mypy strict (72 files)**, zero DDL (`user_version` 5). Shipped
> surface adds the `wiki-sync record` commit-marker CLI (the orchestrator-facing
> `set_source_state`) + vdd-multi hardening (8 MiB `.md` oversize cap, BOM parity,
> full-path config-symlink containment).

1. `pytest -q` ≥ 909 (+4 skipped) + `mypy --strict scripts/` clean at **every** bead;
   `wiki-sync` import carries **no `anthropic`** (grep-guarded).
2. **AC-1/10** — `wiki-sync scan` emits valid plan JSON; two scans of an untouched zone are
   **byte-identical** (entries sorted by POSIX path; no timestamp).
3. **AC-2/2b** — the real `yaml:dbfolder` + Bases/Dataview/folder-note fixtures all `skip`;
   an embedded-dataview content note → `upsert`.
4. **AC-3/4** — extension + tag routing matrix (incl. `.PDF` case, `.excalidraw.md` skip,
   `#wiki/skip`>raw>keep).
5. **AC-5/AC-14** — re-run is a no-op (`sync` row short-circuit); convert+ingest staged output
   in `_raw/.staging/` is **not** re-ingested on the second run.
6. **AC-6** — `--dry-run` leaves vault + DB byte-unchanged; report lists every skip + reason.
7. **AC-8** — `user_version` still 5; only new code = `get/set_source_state` (pure DML).
8. **AC-11/12** — empty/unparseable never raise; no-tag unmappable-type → `skip`; same-stem
   convert sources → distinct `.staging/` targets.
9. **Security** — `.wiki/sync.yaml` anchor-bomb refused; `flock` `LOCK_NB`→`SYNC_IN_PROGRESS`;
   H-6 fence before `summarizing-meetings`; staged write inside-vault + symlink-refused.

## Use Case Coverage

| Use Case | Beads |
|----------|-------|
| UC-1 (transcript → compounding; re-run no-op) | 06, 07, 13, 14, 15 |
| UC-2 (office/PDF convert; `needs-ocr` flag) | 06, 14, 15 |
| UC-3 (mixed: ready upsert + sidecar/draft skip; embedded-view→upsert) | 07, 08, 09, 15 |
| UC-4 (dry-run writes nothing) | 13, 15 |
| UC-5 (per-file failure isolation) | 14, 15 |
| UC-6 (empty zone → empty plan) | 11, 13, 15 |

## Out of scope (per TASK §6)

- Binary-attachment indexing at scale; daily-block dedup; **PDF-OCR completion** (upstream
  Universal-skills — `wiki-sync` only flags `needs-ocr`). No DDL. The optional `stat()`-mtime
  scan short-circuit (W-2) is a deferred YAGNI, not in these beads.
