# 032-04 — `wiki-graph` traversal CLI (16th CLI)

**Owns:** AC-5.1. **Dep:** 032-03. **Detail:** PLAN.md §2 / ADR-004 D6 / Q-032-5.

## Scope
A read-only CLI to query the graph. `wiki-search --edges` rejected (overloads FTS).

## Files
- NEW `scripts/wiki_skills/wiki_graph.py` — subcommands `neighbors <slug>` / `chain <slug>` / `backlinks <slug>`; flags `--kind <ref_type>` / `--direction {in,out,both}` / `--depth N` (capped) / `--vault` / `--db-path` / `--vault-root`. JSON envelope (`python -m json.tool`-friendly). Resolves the index DB via `_common.build_repo_config` (TASK 022 path).
- **DECISION (plan-review 🟡-1): YES, ship a SKILL.md** — `skills/wiki-graph/SKILL.md` + symlinks into `.claude/skills`/`.agent/skills` (consistency with the other 15 `wiki-*` domain skills + agent discoverability). NB these are *domain* skills under `skills/`, NOT framework `.agent/skills/` — created directly like `wiki-search`, no `init_skill.py` gate.
- README CLI count 15→16 (in 032-06 docs).

## Safety
Injection-safe (TASK 013 posture): `--kind` allowlist-validated against the v6 ref_type set; slug bound as a param; **no value echo on error** (`INVALID_KIND`/`INVALID_SLUG`/`VAULT_NOT_FOUND` envelopes + exit codes); `--depth` capped (DoS bound).

## Stub-First (RED → GREEN)
Each subcommand over the fixture graph (deterministic JSON); bad `--kind`/missing slug → clean error envelope + nonzero exit; depth cap enforced; read-only (no DB writes).

## Verify
`mypy --strict`; no `import anthropic`.
