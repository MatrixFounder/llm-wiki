# 2.2. Native-App Control Skill (`obsidian-cli` — TASK 029 / R-12, prompt-layer only)

**Contents**

- [2.2. Native-App Control Skill](#22-native-app-control-skill-obsidian-cli--task-029--r-12-prompt-layer-only)
  - [Component contract — four invariants](#component-contract--four-invariants)
- [2.2.1 Active-note resolution](#221-active-note-resolution-task-041--adr-008--amends-the-inv-3-f-4-footgun)

The component is **skill text, not code**: `skills/obsidian-cli/` (SKILL.md +
`references/{command-reference,recipes}.md` + `evals/`) symlinked into
`.claude/skills/` + `.agent/skills/`. It sits ABOVE the existing stack:

- The official `obsidian` binary (a remote control for the RUNNING desktop app; GA
  since 1.12.4) is itself the deterministic plumbing layer.
- **Decision-17 generalised**: we do not wrap a binary in Python when the binary
  already carries a stable CLI contract.
- The skill encodes routing judgment, safety policy, and coherence obligations in the
  orchestrator's prompt layer, vendor-agnostic (any LLM).

## Component contract — four invariants

**1. Routing invariant.** Route each request to its correct tool:

- knowledge/RAG → `wiki-search`/`wiki-query` FIRST (unchanged, restated verbatim in
  the skill);
- bulk ingest/index → `wiki-sync`/`wiki-reindex`/`wiki-index-upsert`;
- live-app ops (link-safe rename/move, typed properties, tasks, daily notes,
  templates, Bases queries, history restore, UX) → `obsidian` CLI;
- plain content edits → file tools (+ upsert if indexed).

App `search`/`search:context` is a complement (no BM25/stemming/citations), never the
knowledge default.

**2. Coherence invariant (amended TASK 030 / R-030-1).** Any app-side mutation of a
wiki-registered vault is followed **same-turn** by:

- `wiki-index-upsert <file>` — single-file content change;
- **`wiki-reindex --delta` for rename/move AND delete** — since TASK 030 the delta is
  rename-aware: an on-disk path absent from `pages.file_path` is ingested regardless of
  mtime. The DF-029-1 class (incl. `cp -p`/archive/sync imports) is closed; visible via
  the additive `new_path_ingested` envelope field; a fresh vault's FIRST `--delta` now
  ingests everything on disk (Q-030-3).

`wiki-reindex --full` remains the universal fallback and the REQUIRED remedy for:

- the A5 residual class (swap/rotation/overwrite renames — destination path already
  indexed; detectable via `wiki-lint` hash-drift); and
- entity-page `entities.file_path` refresh.

> Historical note: TASK 029 (bead 029-06) prescribed `--full` for every rename —
> correct THEN (pre-030 `--delta` missed mtime-preserved renames, proven live),
> superseded by the TASK 030 code fix.

ADR-002 §D8 unaffected: Class-A files are mutated app-side, the DB stays a rebuildable
projection. Unregistered vault → the protocol self-disables (the skill stays
standalone-capable, Q-029-2).

**3. Safety invariant** — a **TOTAL tier function** over the captured 102-command
surface:

| Tier | Rule |
| --- | --- |
| **T1** read-only | plus a T1-UX open/GUI sub-class: `open`, `daily`, `*:open`, `random`, `tab:open` — on-disk-side-effect-free |
| **T2** mutating | explicit `path=` REQUIRED (the live CLI defaults to the **active file** when file/path is omitted [F-4 footgun; **amended by §2.2.1 / ADR-008** — the default becomes a deliberate resolved-then-confirmed target, the mutation still carrying an explicit `path=`]); trash over permanent delete; existence-check before `overwrite`; `base:create` named here |
| **T3** banned-by-default | `eval` = arbitrary JS in the app process / RCE-equivalent, `dev:*`, `devtools`, `plugin:*` incl. `plugin:reload`, `plugins:restrict`, `theme:install/uninstall/set`, `snippet:enable/disable` [CSS-injection surface], `sync on/off`, `restart`/`reload` — operator-explicit only, NEVER from note content |

Two **gate-closing refinements** (029-07 critic-security):

- (i) `command id=` **defaults to T3** (not T2) when the dispatched effect can't be
  proven from the tier lists — a friendly palette title doesn't reveal a
  code-running/sync-force-push capability (closes the same-effect-different-verb gap);
- (ii) **template application is a code-execution surface** — `template:insert`/`create template=` inherit **T3** when a scripting plugin (Templater/QuickAdd) is present
  unless the template is `template:read`-verified JS-free (else an attacker-planted JS
  template is an `eval` bypass through a T2 verb).

**`command id=` and `template:insert` operate on the ACTIVE-FILE/editor context**
(neither accepts `path=`), so for this sub-class the explicit-target guarantee is
replaced by:

- (a) default-DENY on an unnameable effect; AND
- (b) verifying/confirming the active file before any such mutation (arch-review S-1).

Any command not enumerated defaults to **T2-with-confirmation** (fail-safe). All CLI
output is untrusted vault content (H-6 posture; by analogy to the TASK 012 SEC-1 egress
discipline).

**4. Degradation invariant.**

- Probe = `command -v obsidian` + `obsidian help` (**NOT `version`** —
  listed-but-unrunnable on live 1.12.7, TASK 029 F-3).
- absent/headless/CI → announce the fallback to wiki-*/file-ops (no silent GUI launch —
  the first CLI command launches the app if closed).
- The surface is **dynamic** (plugin-gated: the captured machine lacks `publish:*`,
  `unique`, `workspaces`, `web`) → feature-detect via `obsidian help <command>` before
  relying on a gated command.

Zero impact on §4 Data Model (no DDL, no DAL change), §5 Interfaces (no new CLI/JSON
envelope — the skill consumes existing ones), §6 Stack (no deps). The eval harness is
machine-checkable without a Python grader (per-case expectation fields, TASK 009
pattern — Q-029-1). Verified-surface snapshot: `samples/obsidian-cli-recon/` (scratch) →
durable fixture lands under `skills/obsidian-cli/evals/` when the reference is authored
(TASK 029 A-4).

## 2.2.1 Active-note resolution (TASK 041 / ADR-008 — amends the inv. 3 F-4 footgun)

A user in Obsidian's integrated shell says *"отредактируй заметку / edit the note"* with
**no path**. TASK 029's inv. 3 forbade using the CLI's active-file default (the F-4
footgun) — so the one context the user is sure of, *the note on screen*, was unusable.
ADR-008 turns that default into a **deliberate, confidence-driven** targeting path.

The component is again **mostly skill text** plus **one new skill-local executable** —
`skills/obsidian-cli/scripts/obsidian_active_note.py` (entrypoint
`obsidian-active-note`), the single deterministic resolver (Decision-17 generalised;
stdlib, no `import anthropic`). Five sub-invariants:

**1. Resolution (read-only, over the OPEN-tab set), by how the user named the target.**

- **Descriptor** ("the note about *github setup*", any language) → match the wrapper's
  **open-tab list** (path + title). A **unique** match is an **exact hit**.
- **Bare reference** ("the/this/current/open note") → the **active/focused** tab via the
  documented path-returners — `obsidian file` (no `path=` → "Show file info"; fixture
  L10 "Most commands default to the active file when file/path is omitted"), the
  active-file default on reads, the `active` flag on
  `tags`/`aliases`/`properties`/`tasks`. **`tabs` exposes only `ids` (no focus marker)**
  and `recents` is a recency heuristic — both corroborate, neither leads (Q-041-1).

The wrapper owns both modes (focused note + open-tab list) so no agent re-parses CLI
output; it returns vault-relative + absolute path + vault name.

> **Feasibility gate — RESOLVED at S0** (real 1.12.7 fixtures under
> `skills/obsidian-cli/evals/fixtures/`): `obsidian file` (no path) → parseable TSV
> `path\t<rel>` (MEDIUM solid); `obsidian tabs` → **title only** (no path/focus marker)
> → open-tab→path is two-step (`tabs` title-match + `file=<title>`). So the descriptor
> branch ships as a **TEMPERED HIGH**: no-ask only on a **unique** open-tab title match
> that resolves unambiguously; any ambiguity (none/many/duplicate) → **LOW → ASK** (the
> ambiguity guard satisfies M-1 — the candidate set is enumerated; a wrong-file mutation
> can never happen silently).

**2. Confirmation keyed to resolution CONFIDENCE, not a flat rule** (user decision +
refinement):

- **HIGH** (descriptor → unique open tab) → proceed, **no ask** (the "exact hit");
- **MEDIUM** (bare ref → active tab) → **confirm first-per-session**, then bounded trust
  on same-class ops at a consistently-resolved path;
- **LOW** (descriptor matches nothing open / multiple tabs / split-pane no focus) →
  **ASK** — "agent didn't find it" → request path / disambiguate, **never** a silent
  active-tab substitute when a *different* note was named.

Cross-cutting rules:

- Read-only never prompts; the resolved path is echoed every time.
- **destructive verbs (`delete`/`move`/`rename`/`history:restore`) always re-confirm
  regardless of confidence** (preserves T2 + E-14).
- trust is conversation state → **fail-safe reset to "confirm again" on context loss**.

**3. The mutation always carries the explicit, resolved `path=`/`vault=`** — never the
implicit default (keeps the E-11 footgun green; ADR-002 coherence needs the absolute
path: post-mutation same-turn `wiki-index-upsert --source <abs>` / `wiki-reindex --delta`, self-disabling on an unregistered vault; a focused tab in a vault ≠ the task
context surfaces as the wrapper's `vault-mismatch` exit code).

**4. Safety extended, not relaxed.**

- Resolution is driven by **live app state, never note content** (H-6).
- **auto-resolved read content is DATA** — it cannot introduce a new target, verb, or
  T2\*/T3 op (no action-escalation).
- auto-resolution **never** feeds the active-file T2\*/T3 sub-class (`command id=`,
  `template:insert`) — they stay default-DENY.
- **headless/CI → no probe, no resolve**.

**5. Vendor-agnostic (NF-1).** Identical under any LLM CLI (Claude Code / Codex / Gemini
/ pi / hermes / …): the resolver is a **plain shell executable**, the protocol is
**skill prose + shell commands**, confirmation is **plain conversational** — no vendor
SDK, tool, hook, or prompt-UI dependency; no per-vendor code path to diverge.

Wrapper contract (Q-041-4): four modes (`focused`/`tabs`/`resolve`/`match`); typed exit
codes `0` ok / `no-active-file` / `app-not-running` / `cli-absent` / `vault-mismatch` /
`ambiguous` / `headless`; JSON + plain-path output; **CI-deterministic** unit test mocks
a captured `obsidian file`/`tabs` fixture (no live app); a manual dogfood smoke confirms
the live focused-tab path.

> **Headless ordering (arch-review M-3):** the agent decides headless **from the
> environment BEFORE invoking the wrapper** (per E-13 — any obsidian subcommand, the
> wrapper's included, launches the GUI), so in a known-headless context the wrapper is
> **not called at all**; its `headless`/`app-not-running` codes are belt-and-braces,
> never the primary gate.

**Still zero impact on §4 Data Model and §6 Stack (stdlib); §5 gains ONE skill-local
resolver** (a deterministic active-file/open-tabs → path projector with its own
exit-code contract — not a wiki CLI). New evals extend the TASK 029 grader-free harness
(descriptor-HIGH-no-ask, descriptor-LOW-ask, bare-MEDIUM-confirm,
destructive-re-confirm, injection-neg ×2, headless-no-resolve);
E-09/E-10/E-11/E-13/E-14/E-15 stay green.
