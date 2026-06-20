# ADR-008 — Active-note resolution (the active-file default becomes a deliberate, confirmed target)

**Status:** Accepted (TASK 041, shipped 2026-06-20) · **Date:** 2026-06-20 · **Supersedes:** none ·
**Amends:** the `obsidian-cli` **Safety invariant** F-4 footgun rule (ARCHITECTURE §2.2 inv. 3;
SKILL.md "Targeting discipline") · **Relates:** ADR-002 (Class A/B/C coherence), TASK 029 (the
`obsidian-cli` skill), H-6 (untrusted content).

## Context

The official `obsidian` CLI **defaults to the active file** when `path=`/`file=` is omitted
(help fixture L10: *"Most commands default to the active file when file/path is omitted"*). TASK 029
classified this as **F-4, a "silent footgun"** and adopted a blunt guard: *every mutating command
MUST carry an explicit `path=`; never rely on the active-file default.* Correct as a safety floor —
but it throws away the one piece of context a user in Obsidian's integrated shell is most sure of:
**the note they are looking at.** So *"отредактируй заметку / edit the note"* (no path) forces the
agent to stop and ask, when the answer is on screen.

The danger F-4 guards against is a **blind** mutation of an *unknown* active file. That danger is
removed if the agent **resolves** the active file to a concrete path *read-only*, **shows** it, and
acts on an **explicit** `path=` — the determinism + index-coherence the floor wants, plus the UX the
user asked for. The live app already exposes the resolver, read-only: `obsidian file` (no `path=` →
"Show file info" of the active file), the active-file default on read commands, and the `active`
flag on `tags`/`aliases`/`properties`/`tasks`. (`tabs` exposes only `ids` — **no focus marker** — so
it is corroboration, not the lead.)

## Decision

**Turn the active-file default from a banned footgun into a deliberate, *confidence-driven*
targeting path.** When the target is pathless AND the CLI is present + the app is running
(non-headless), the agent resolves an **open** note read-only and asks **only when it cannot
confidently identify one**:

1. **Resolve read-only, over the open-tab set.** Two sub-cases by how the user named the target:
   - **Descriptor** ("the note about *github setup*") → match against the **open tabs** (path/title).
     A **unique** match is an **exact hit** (HIGH confidence) — proceed **without asking**.
   - **Bare reference** ("the/this/current/open note", any language) → the **active/focused** tab via
     the documented path-returners — `obsidian file` / the active-file default / an `active`-flagged
     read (MEDIUM confidence — nothing corroborates the match). `tabs`/`recents` corroborate only
     (`recents` is a heuristic, not the focused tab).
   Resolution yields **vault-relative + absolute path + vault name**. A single **skill-local wrapper
   `obsidian-active-note`** owns the chain — both the focused note AND the open-tab list (path+title)
   for descriptor matching (the one new piece of code — Decision-17-generalised deterministic
   plumbing; no `import anthropic`, stdlib only).
2. **Confirmation is keyed to resolution CONFIDENCE, not a flat rule.**
   - **HIGH** (descriptor → unique open tab): proceed, **no ask** (the user's "exact hit").
   - **MEDIUM** (bare ref → active tab): **confirm first-per-session**, then BOUNDED trust —
     afterwards same-class ops on a consistently-resolved path proceed silently (path still echoed).
   - **LOW** (descriptor matches **nothing open** / **multiple** open tabs / split-pane, no focus):
     **ASK** — "the agent didn't find it" → request the path or disambiguate; never silently fall
     back to the active tab when the user named a *different* note.
   - **Read-only never prompts.** **Destructive verbs (`delete`/`move`/`rename`/`history:restore`)
     always re-confirm regardless of confidence** (preserves T2 + E-14).
   - Trust is conversation state: **lost context ⇒ fail-safe reset to "confirm again."**
3. **The actual op always carries the explicit, resolved `path=`/`vault=`** — never the implicit
   default (keeps E-11 green; coherence needs the absolute path).

**Safety stays intact and is extended.** Resolution is driven by **live app state, never note
content** (H-6). Auto-resolved read content is **DATA** — it cannot introduce a new target, a new
verb, or a T2\*/T3 op. Auto-resolution **never** feeds the active-file T2\*/T3 sub-class
(`command id=`, `template:insert`) — they stay default-DENY. **Headless/CI → no probe, no resolve**
(any `obsidian` call launches the GUI). The F-4 rule is **amended, not deleted**: explicit `path=`
is still required on the mutation — *supplied directly, or resolved-and-confirmed*.

**Vendor-agnostic by construction.** The feature must behave identically under any LLM CLI
(Claude Code, Codex, Gemini, pi, hermes, …) — matching the skill's existing "any LLM" contract. So
it lives entirely in (a) the **plain shell executable** `obsidian-active-note` (stdlib; no vendor
SDK) and (b) **skill prose + shell commands** any model reads. Confirmation is **plain conversational
ask/await** — never a vendor-specific prompt UI/hook — and "session" means the agent's current
conversation, whatever the host. There is no per-vendor code path to diverge.

## Consequences

**Positive.** The user's most reliable context (the focused note) becomes usable with one
per-session confirmation; the footgun's actual danger (blind mutation) is closed by resolve-show;
determinism + ADR-002 coherence are preserved (explicit absolute path throughout). The
`obsidian-active-note` wrapper gives one deterministic, **CI-mockable** resolver (typed exit codes:
`no-active-file`/`app-not-running`/`headless`/`cli-absent`/`vault-mismatch`) instead of ad-hoc
output parsing.

**Cost / risk.** It softens a stated safety floor — mitigated by (a) read-only resolution, (b)
the destructive-verb carve-out (E-14), (c) the action-escalation guard (H-6), (d) the explicit
`path=` on the mutation (E-11). One new skill-local executable (outside the `mypy --strict scripts/`
tree — typed lightly, stdlib-only). Live-app dependence: the focused-note path on split panes is a
dev-time feature-detect (Q-041-1); on ambiguity the agent re-confirms regardless of session trust.

**Alternatives rejected.** (a) Keep F-4 absolute — ignores the user's request and the on-screen
context. (b) Rely on the implicit active-file default directly (omit `path=`) — re-opens the blind
mutation, breaks E-11, and gives coherence no absolute path. (c) Gate on detecting the Obsidian
integrated terminal — needs a signal that may not exist; the app-running + no-path trigger is
strictly simpler and works from any shell (user decision).

## Verification

New evals (assert against the wrapper exit-code contract): **descriptor → unique open tab = HIGH,
no ask**; **descriptor → zero/multiple open tabs = LOW, ask** ("not found"); bare ref → active tab =
MEDIUM, confirm-first-per-session; **+ destructive-verb re-confirm**; injection-neg ×2 (note content
sets neither target nor escalates action); headless → no-resolve. Every resolved mutation carries an
explicit `path=`. Existing never-relax evals E-09/E-10/E-13/E-15 + the **E-11 footgun** + **E-14** stay
green. Wrapper contract test is CI-deterministic (mockable against a captured `obsidian file`/`tabs`
fixture); a manual dogfood smoke confirms the live focused-tab path. `skill-validator` clean on the
modified skill.

**Feasibility entry-gate — RESOLVED at S0** (real 1.12.7 fixtures committed under
`skills/obsidian-cli/evals/fixtures/`). `obsidian file` (no path) yields parseable TSV
`path\t<vault-rel>` (M-2 ✓ — MEDIUM is solid; the `No active file` error is the `no-active-file`
signal). `obsidian tabs` enumerates open tabs by **title only** (`[view-type] Title`; no path, no
focus marker) → open-tab→path is a **two-step** (`tabs` title match, then `file=<title>` → path). So
the descriptor branch **ships as a *tempered* HIGH**: no-ask **only** when the descriptor matches
exactly ONE open `[markdown]` tab AND it resolves unambiguously; **any** ambiguity
(none/many/duplicate title) **degrades to LOW → ASK** — a wrong-file mutation can never happen
silently (arch-review M-1 satisfied: the candidate set is enumerated, with a hard ambiguity guard).
Narrower than full no-ask, broader than the contingency's confirmed-MEDIUM; it best honors the user's
"exact hit, no ask". **Headless ordering (M-3):** headless is decided from the environment BEFORE the
wrapper is invoked (E-13 — any subcommand launches the GUI); the wrapper's `WIKI_HEADLESS=1`
belt-and-braces code is never the gate. The `obsidian-active-note` resolver
(`focused`/`tabs`/`resolve`/`match`) is contract-tested in `tests/test_obsidian_active_note.py`
against the committed fixtures.
