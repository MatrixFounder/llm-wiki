# Architecture Review — TASK 041 (active-note resolution / ADR-008)

**Reviewer:** Architecture Reviewer (VDD gate, Architecture→Planning)
**Scope reviewed:** `docs/ARCHITECTURE.md` §2.2.1 (new) + §2.2 inv.3 cross-ref + §7 sentence; `docs/adr/ADR-008-active-note-resolution.md`; `docs/architectures/open-questions.md` §11g (Q-041-1…8); `docs/TASK.md` (TASK 041).
**Verified against:** `skills/obsidian-cli/evals/evals.json` (E-01…E-15), `skills/obsidian-cli/references/command-reference.md`, `skills/obsidian-cli/evals/fixtures/obsidian-help-1.12.7.txt`, `skills/obsidian-cli/SKILL.md`, `CLAUDE.md` durable invariants.

**Verdict: APPROVED WITH COMMENTS.** No blocking data-model, security, or invariant violations. Coherent with the never-relax evals, the H-6 posture, the zero-DDL / no-`anthropic` / no-deps invariants, and NF-1. The closest-to-blocking issue is a **resolver-feasibility gap on the HIGH-confidence (no-ask) descriptor branch** — graded 🟡 (not 🔴) because the design self-flags it (Q-041-1) and the safe degradation (LOW→ASK) is the design's own default, so the worst case is "ask," not "mutate the wrong file." Planning must pin the contingency before any HIGH no-ask path ships.

## 🔴 CRITICAL (blocking)
None. The four high-risk invariants hold:
- **Never-relax evals satisfiable** — E-09/E-10/E-15 (inv.4 live-state-not-content + the M2 action-escalation guard/UC-6b), E-13 (inv.4 headless no-probe/no-resolve), E-11 (inv.3 explicit resolved `path=`), E-14 (inv.2 destructive verbs always re-confirm).
- **CLAUDE.md invariants** — no `import anthropic` (stdlib wrapper), zero DDL (`user_version` 7 untouched), zero deps, Class A/B/C coherence (reuses existing `wiki-index-upsert`/`wiki-reindex --delta`, no DAL change).
- **Data Model untouched** — §4 not edited; wrapper = path projector, not a DB writer.
- **NF-1 vendor-agnostic** — no per-vendor code path; `vault.claude-settings.json` correctly scoped as a Claude convenience.

## 🟡 MAJOR

### M-1 — The HIGH (no-ask) descriptor branch rests on open-tab enumeration the captured CLI doesn't visibly expose.
The HIGH branch skips confirmation, so it needs the wrapper to enumerate **open tabs with path + title**. But the fixture shows `tabs` exposes only `ids` (L344–345; no path/title/`format=`), `recents` is a whole-vault recency heuristic (not the open set), and **no real `obsidian tabs`/`obsidian file` output is captured anywhere** (`samples/obsidian-cli-recon/` holds only the help listing). The no-ask branch — the one place a wrong resolution mutates silently — rests on an unproven capability.
**Fix (Planning gate):** (a) capture real `obsidian tabs`/`tabs ids`/`obsidian file` output into a committed fixture under `skills/obsidian-cli/evals/fixtures/`; (b) if open-tab path+title is NOT recoverable, **demote HIGH → confirmed-MEDIUM** (descriptor → resolve focused tab, show it, confirm-first-per-session) and update §2.2.1/ADR-008/R-2a — never ship a no-ask path whose resolver can't enumerate the candidate set; (c) the wrapper contract test (DoD §3a) asserts against the real fixture.

### M-2 — "`obsidian file` (no path) returns the active file's PATH" is inferred, not verified.
`file` = "Show file info" (L117), `format=` "—" (text-only), so the wrapper must scrape free text; the `active`-flag fallbacks return tag/alias/property lists, not a path. Q-041-1's own residual ("which command reliably returns the active file's path") is genuinely open and the whole MEDIUM path depends on it.
**Fix:** same fixture-capture remedy; elevate Q-041-1 from "residual" to a **Planning entry gate**; pin the parse target in the contract-test fixture before the wrapper contract is frozen.

### M-3 — The wrapper's `headless` exit code reintroduces the GUI-launch E-13 forbids.
E-13: in headless, treat the CLI as unavailable **without probing** (any subcommand launches the GUI). But the wrapper IS a chain of obsidian subcommands; returning a `headless` code means it already probed.
**Fix (Planning):** the agent's **headless determination happens BEFORE invoking the wrapper** (env signal — CI / no-display, per existing E-13 discipline); the wrapper's `headless`/`app-not-running` codes are belt-and-braces, never the primary gate. Document in §2.2.1 that in a known-headless context the wrapper is **not called at all**.

## 🟢 MINOR
- **m-1 (YAGNI).** The HIGH/MEDIUM/LOW model is a faithful encoding of R-2, not gold-plating. If M-1 forces HIGH→MEDIUM, it collapses to a cleaner two-level (confirmable / ask) that still satisfies every UC — treat that as the fallback shape.
- **m-2.** `vault-mismatch` is the right call but shares M-2's "does `file` report the active vault?" uncertainty — fold into the fixture capture so the branch is fixture-backed.
- **m-3.** SKILL.md `## Targeting discipline` (`:52–55`) still states the unqualified footgun rule with no forward-pointer to the resolution protocol — a developer-phase `skill-enhancer` edit (already required by DoD #4); just don't leave the SKILL.md prose contradictory.
- **m-4.** Doc-size/no-drift OK — ARCHITECTURE in INDEX-mode, §2.2.1 inserted in place, ADR-008 a proper new ADR, §11g appended.

## Routing
M-1/M-2/M-3 are **Planning entry gates**, not re-architecting: (a) commit real `obsidian file`/`tabs` fixtures, (b) a one-line contingency demoting HIGH→confirmed-MEDIUM if open-tab enumeration is unavailable, (c) the headless-before-wrapper ordering note. None block the Architecture→Planning transition; they constrain what Planning may assume.
