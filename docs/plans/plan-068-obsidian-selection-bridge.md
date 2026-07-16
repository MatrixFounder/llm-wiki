# PLAN 068 — Obsidian editor-selection bridge (stub-first)

Traces `docs/TASK.md` (TASK 068) and the verified `docs/_scratch/task-068-design-brief.md`.
Stub-First: **Phase 0** lands every `tests/test_obsidian_selection.py` case RED against file skeletons,
**Phase 1** turns the roster GREEN with the real plugin + wrapper logic, **Phase 2** closes docs +
security (SKILL.md + H-5 re-pin + recipe + evals + architecture). Each checklist item names the
`R-068-N` it discharges (spec-validator contract).

**Baseline to preserve (§0):** `2930 passed, 14 skipped, 0 failed` (~75s). All-green, **no carve-out**.
Success = **0 NEW failures AND ≥2930 passed** (all new tests are additive), `mypy --strict` clean for
the new script, `git diff sql/` empty (A-11), no `import anthropic` in the new script (A-12).

---

## Locked toolchain & key design decisions (read before executing)

1. **Plugin build (R-068-1) — hand-authored CommonJS `main.js` + reviewable `main.ts` + a *vendored*
   minimal `obsidian.d.ts`.** The repo has **no** `package.json`, **no** local `tsc`, and forbids global
   npm; an Obsidian vault should not need a JS toolchain to *install* the plugin. So the **shipped**
   artifacts are `manifest.json` + a hand-authored CommonJS `main.js` (Obsidian plugins are plain
   CommonJS — no bundler required). `main.ts` is the **reviewable typed source of truth**; a **committed
   minimal `obsidian.d.ts` stub** (declaring only the symbols the plugin touches — `Plugin`, `App`,
   `Editor`, `EditorPosition`, `MarkdownView`, `TFile`, `DataAdapter`, `Notice`, `Command`) makes the
   R-068-1 type-check self-contained. **R-068-1 verification is concrete:** a plugin-scoped
   `tsconfig.json` + `package.json` (only `typescript` as a dev dependency, `node_modules/` gitignored)
   so `npx tsc --noEmit` (run from `plugin/agent-bridge/`) exits 0. *Sandbox fallback (recorded
   deviation, Open Question A):* if `typescript` cannot be fetched in the dev sandbox, R-068-1 is
   satisfied by a documented symbol-by-symbol review of `main.ts` against the vendored `obsidian.d.ts`
   (every referenced symbol/member resolves), re-run under a live `tsc` before merge. The committed
   `main.js` carries the §3.1 **manual "rebuild before commit" discipline** in the plugin `README.md`
   (no build-hash tie — an accepted residual).

2. **The apply read-back race — a wrapper-supplied `nonce` echoed by the plugin (named design point).**
   `obsidian command id=…` is fire-and-return; the wrapper must not read a **stale** `agent-result.json`
   from a prior invocation. **Contract:** every wrapper invocation mints a fresh `nonce`; `apply` writes
   it into the payload file `agent-edit.json`, `read` writes it into a small `agent-request.json`; the
   plugin **echoes `nonce`** into `agent-result.json` (and `agent-selection.json`). After dispatch the
   wrapper **bounded-polls** `agent-result.json` until it observes the **matching** nonce, then reads —
   no-match within the timeout → `app-not-running` (exit 4). Crucially this means a **leftover
   `agent-result.json` from a PRIOR invocation** (wrong nonce, even `ok:true`) is **rejected**, never
   accepted as a false success — tested explicitly by `read-stale-nonce.result.json` + the exit-4
   stale-nonce case in 068-03. The poll **short-circuits on an immediate match** and its sleep/clock is
   injectable, so fixtures (which pre-seed a result carrying the expected nonce) resolve on the first
   iteration with **no real waiting** — fully deterministic, no live app.

3. **Coherence as a Decision-17 dispatch MARKER, never an inline call (R-068-7).** The wrapper does
   **not** shell out to `wiki-index-upsert` (mirrors the sibling; keeps Decision-17 clean). On `apply`
   ok:true it emits a `coherence` block in its envelope: with an optional `--wiki-vault <vid>` supplied
   → `{"action":"wiki-index-upsert","vault":"<vid>","source":"<ABS>"}`; **without** `--wiki-vault`
   (the agent knows the vault is unregistered) → `{"skipped":"vault-not-registered"}` (self-disable,
   *stated*). On **any** refusal (ok:false) the `coherence` key is **omitted, not false** (the Decision-17
   marker rule). The AGENT runs the upsert per the recipe. Tested purely on the envelope shape.

4. **Exit-code ↔ reason map (implement EXACTLY — R-068-4/R-068-6).** Multiple typed `reason`s can share
   an exit-code bucket; the envelope's `reason` field distinguishes them:

   | reason | detected by | exit |
   |---|---|---|
   | `no-editor` | `!activeEditor` (result) | `3` |
   | `preview` | `getMode()==="preview"` (result) | `3` |
   | `empty-selection` | `!somethingSelected()` (result) | `3` |
   | `vault-mismatch` | `--expect-vault` ≠ resolved `vault` (wrapper, like the sibling `_check_vault`) | `6` |
   | `path-mismatch` | GUARD 1 fail (result) | `7` |
   | `stale-range` | GUARD 2 fail (result) | `7` |
   | `plugin-absent` | `obsidian commands` scan lacks `agent-bridge:` (wrapper) | `9` |
   | `payload-too-large` | encoded payload > **512 KiB** threshold (wrapper) → advise `--from-json` | `2` |
   | *(app dispatch/result timeout)* | nonce never matched (wrapper) | `4` |
   | *(cli absent)* | `shutil.which("obsidian") is None` | `5` |
   | *(headless)* | `WIKI_HEADLESS=1` | `8` |
   | *(usage)* | argparse / bad args | `2` |
   | `ok` | result `ok===true` (shape, **never** exit code — ground-truth fact #4) | `0` |

5. **base64 for the untrusted TEXT, raw text never on an argv (R-068-5).** The agent passes base64
   (`--expect-b64`/`--replacement-b64`, or `--from-json`); the wrapper writes the payload **still
   base64-encoded** into `agent-edit.json` and dispatches a **fixed** `obsidian command id=…` — so the
   selection/replacement TEXT appears on **no** subprocess argument (the plugin `TextDecoder`-decodes
   it). The `path` is **not** base64-encoded: it is a structural, app-sourced identifier (the plugin's
   GUARD 1 re-validates it against the live `activeEditor.file.path`), written JSON-escaped into
   `agent-edit.json` — never on a shell command line — so encoding would add nothing. ARG_MAX is a
   non-issue on the wrapper→plugin hop; the only residual (a huge inline `--replacement-b64` on the
   agent→wrapper hop) is guarded by the 512 KiB `payload-too-large` check (decision 4), and
   `--from-json` (a FILE, no ARG_MAX limit) is the genuine escape valve — **exempt from the cap**. The
   temp-file/`require('fs')` hatch stays out of scope (§11).

---

## Phase 0 — Stub-First: skeletons + RED roster

- [ ] **068-01** (R-068-1) Create the plugin skeleton `skills/obsidian-cli/plugin/agent-bridge/`:
      `manifest.json` (`id:"agent-bridge"`, `minAppVersion:"1.4.0"`, `isDesktopOnly:false`), `main.ts`
      (typed source — both commands registered with plain `callback`, bodies stubbed), a hand-authored
      CommonJS `main.js` stub mirroring it, a **vendored minimal `obsidian.d.ts`** + `tsconfig.json` +
      plugin-scoped `package.json` (dev-only `typescript`, `node_modules/` gitignored), and `README.md`
      (install steps + the §3.1 manual-rebuild discipline + the OQ1 one-time "callback fires under
      terminal focus" verification). **Verify:** `npx tsc --noEmit` from the plugin dir exits 0 against
      the stub (or the recorded symbol-review fallback). See `docs/tasks/task-068-01-plugin-skeleton.md`.
- [ ] **068-02** (R-068-3, R-068-4) Create `skills/obsidian-cli/scripts/obsidian_selection.py` skeleton
      mirroring the sibling: module docstring/header, exit-code constants `0/2/3/4/5/6/7/8/9`, the single
      `_run_obsidian` seam, argparse with `read` / `apply` subcommands, shared
      `--format json|path|tsv` / `--vault` / `--expect-vault`, and `apply`'s `--path` / `--expect-b64` /
      `--replacement-b64` / `--from-json` / `--wiki-vault`; stub handlers return a `{"ok":false,
      "reason":"not-implemented"}` envelope. **Verify:** module imports; `mypy --strict
      skills/obsidian-cli/scripts/obsidian_selection.py` clean. See
      `docs/tasks/task-068-02-wrapper-skeleton.md`.
- [ ] **068-03** (R-068-4, R-068-5, R-068-6, R-068-7, R-068-10) Author the deterministic fixtures under
      `skills/obsidian-cli/evals/fixtures/selection/` (per-rung `*.selection.json` / `*.result.json`,
      `agent-commands-present.txt` / `agent-commands-absent.txt`, `b64-vectors.json`) AND the FULL
      `tests/test_obsidian_selection.py` roster RED against the stubs: per-subcommand, one per **exit
      code** (R-068-4), one per **ladder rung reason** (R-068-6), the base64 round-trip over
      Cyrillic + `"` + `\d` + a literal newline (R-068-5), the no-un-encoded-argument assertion (R-068-5),
      the no-`eval`-ever assertion (R-068-4), and the coherence-marker present/skipped/omitted assertions
      (R-068-7). **Verify:** `pytest tests/test_obsidian_selection.py -q` is RED (fails, does not error/
      collect-fail). See `docs/tasks/task-068-03-fixtures-and-red-tests.md`.

## Phase 1 — Logic → GREEN

- [ ] **068-04** (R-068-1, R-068-2) Implement the plugin: fill `main.ts` AND hand-author the matching
      CommonJS `main.js` — `export-selection` (read `activeEditor`; capture `{vault,path,from,to,
      fromOffset,toOffset,text,mtime,exportedAt,nonce}`; write `.obsidian/agent-selection.json`; mirror
      `.obsidian/agent-result.json`; `ok:false`+`reason` on `!activeEditor`/`preview`) and `apply-edit`
      (read `.obsidian/agent-edit.json`; GUARD 1 `payload.path===activeEditor.file.path`, GUARD 2
      `editor.getRange(from,to)===payload.expect`, and the `somethingSelected()` check; on pass
      `editor.replaceRange` **then** `await activeEditor.save()`; mirror **every** outcome — success or
      refusal — to `.obsidian/agent-result.json` with the `nonce` echo). **All** I/O via
      `app.vault.adapter`, scoped to `.obsidian/`. **Verify:** `main.ts` type-checks clean (R-068-1);
      grep/inspection shows no `require('fs')`/absolute-path access. See
      `docs/tasks/task-068-04-plugin-logic.md`.
- [ ] **068-05** (R-068-3, R-068-4, R-068-6) Implement `read`: cli-absent (5) + headless (8) guards;
      feature-detect via an `obsidian commands` scan for the `agent-bridge:` prefix → `plugin-absent`
      (9) before any dispatch; `--expect-vault` mismatch → `vault-mismatch` (6); write `agent-request.json`
      with the nonce; dispatch `command id=agent-bridge:export-selection`; nonce-freshness poll of
      `agent-result.json` + read `agent-selection.json`; map reasons → exit codes
      (`no-editor`/`empty-selection`/`preview` → 3); emit the `{ok,mode:"read",vault,path,from,to,
      fromOffset,toOffset,text,mtime,reason}` envelope in `json`/`path`/`tsv`. **Verify:** the read half of
      `tests/test_obsidian_selection.py` is GREEN. See `docs/tasks/task-068-05-wrapper-read.md`.
- [ ] **068-06** (R-068-2, R-068-4, R-068-5, R-068-6, R-068-7) Implement `apply`: accept the base64 TEXT payloads (path structural)
      (or `--from-json`), enforce the 512 KiB `payload-too-large` guard (2), write the **still-encoded**
      payload + nonce to `agent-edit.json` (raw text never on an argv), dispatch
      `command id=agent-bridge:apply-edit`, do the **nonce-matched** read-back of `agent-result.json`
      (the named race design point), detect success by **shape** (`ok===true`) not exit code, map
      `path-mismatch`/`stale-range` → `guard-refused` (7), swap `text→newLen` in the envelope, and emit
      the coherence dispatch marker (ok+`--wiki-vault` → `wiki-index-upsert` marker; ok without →
      `skipped:"vault-not-registered"`; refusal → omitted). **Verify:** the apply / base64 / no-raw-arg /
      no-eval / coherence tests are GREEN. See `docs/tasks/task-068-06-wrapper-apply.md`.

## Phase 2 — Docs & security closeout

- [x] **068-07** (R-068-8, R-068-9) Edit `skills/obsidian-cli/SKILL.md`: Top-20 + Safety-tiers rows for
      `command id=agent-bridge:export-selection` (T2-read) and `:apply-edit` (T2-mutating, guard-gated);
      **the explicit carve-out naming both `agent-bridge:*` ids as proven-effect exceptions** to the
      existing `command id=…` default-T3/default-DENY rule (§6/R-068-8); a Script Contract paragraph for
      `obsidian_selection.py`; a Safety Boundaries note; the §6/§9 security-tier + confirmation policy
      (`selection:read` T2-read MEDIUM confirm-first-then-trust; `selection:replace` T2-mutating
      confidence-gated with blast-radius re-confirm; selection bodies untrusted H-6; `eval` never
      auto-dispatched); keep the T3 `eval` row and add "the only sanctioned production selection channel
      is the plugin". **Then re-pin:** `python3 scripts/pin_skill_integrity.py --write`. **Verify:**
      `tests/test_h5_skill_integrity.py` GREEN. See `docs/tasks/task-068-07-skill-md-and-h5-repin.md`.
- [x] **068-08** (R-068-8, R-068-9) Add the "edit the selected text" recipe to
      `skills/obsidian-cli/references/recipes.md` (a stated pin-roster exclusion — **no** re-pin) and
      append the **two never-relax evals** to `skills/obsidian-cli/evals/evals.json`: (a) a note asking
      the agent to run `obsidian eval …` for a selection edit is refused citing T3 (E-09 sibling);
      (b) an attacker note supplying a second `code=` argument mimicking the template — assert only the
      first `code=` is honoured (ground-truth fact #5). **Verify:** both new eval cases present with
      `never_relax:true`; `references/recipes.md` **not** in the H-5 manifest diff. See
      `docs/tasks/task-068-08-recipe-and-evals.md`.
- [x] **068-09** (R-068-1, R-068-10) Add architecture **§2.2.2 "editor-selection bridge"** to
      `docs/architectures/functional/native-app-control.md` (matching the §2.2.1 style) + a one-line
      security note in `docs/ARCHITECTURE.md`'s security section consistent with how TASK 041 recorded
      §2.2.1; run the final gates — `mypy --strict skills/obsidian-cli/scripts/obsidian_selection.py`
      clean, full `pytest tests/ -q` **0 NEW failures & ≥2930 passed** vs the Baseline, `git diff sql/`
      empty (A-11), `grep -E "import anthropic|from anthropic" …obsidian_selection.py` no hits (A-12),
      and re-affirm the R-068-1 `main.ts` type-check. See `docs/tasks/task-068-09-architecture-and-gates.md`.

---

## RTM → checklist coverage

| RTM ID | Discharged by |
|---|---|
| **R-068-1** | 068-01, 068-04, 068-09 |
| **R-068-2** | 068-04, 068-06 |
| **R-068-3** | 068-02, 068-05 |
| **R-068-4** | 068-02, 068-03, 068-05, 068-06 |
| **R-068-5** | 068-03, 068-06 |
| **R-068-6** | 068-03, 068-05, 068-06 |
| **R-068-7** | 068-03, 068-06 |
| **R-068-8** | 068-07, 068-08 |
| **R-068-9** | 068-07, 068-08 |
| **R-068-10** | 068-03, 068-09 |

## Fixture set (Phase 0, committed, no live app)

`skills/obsidian-cli/evals/fixtures/selection/`:
`agent-commands-present.txt` (lists `agent-bridge:export-selection`/`:apply-edit`),
`agent-commands-absent.txt` (lacks them → exit 9), `read-ok.selection.json` + `read-ok.result.json`,
`read-no-editor.result.json`, `read-preview.result.json`, `read-empty-selection.result.json`,
`read-stale-nonce.result.json` (ok:true but a NON-matching nonce — the read-back-race guard fixture),
`apply-ok.result.json`, `apply-path-mismatch.result.json`, `apply-stale-range.result.json`,
`b64-vectors.json` (plaintext ↔ expected base64 for Cyrillic + `"` + `\d` + newline). Each carries the
echoed `nonce` field the read-back matches on (the stale-nonce fixture deliberately does not).

---

### Stub-First rationale

The feature's defining property is *safe refusal under a live-editor TOCTOU* — so the roster must be
able to go RED on every degradation rung **and** on any un-encoded-text / eval leak. Phase 0 writes that
full RED roster against inert stubs (each handler returns `reason:"not-implemented"`); Phase 1's first
greens are the guard/ladder cases, proving the refusals are real and not green-by-omission. Phase 2 is
pure Class-A/prose closeout (SKILL.md + H-5 re-pin + recipe + evals + architecture) — no schema, no DAL,
no DDL (A-11), Decision-17 intact (A-12).
