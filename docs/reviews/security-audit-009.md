# Security Audit — TASK 009 (`wiki-verify` critic-prompt hardening)

**Gate:** Execution→Merge (C3 mandatory — SECURITY-SENSITIVE prompt surface) ·
**Auditor:** security-auditor (independent) · **Date:** 2026-05-29
**Verdict:** **PASS-WITH-NOTES** (`has_critical_issues: false`, 0 CRITICAL / 0 HIGH)

No CRITICAL/HIGH on the prompt surface. H-6 armor preserved **byte-for-byte** (banner + output
contract byte-identical to HEAD; diff touches only the lens section). Few-shot defang control is
**real + regression-proof** against de-fencing existing canaries (auditor mutated SKILL.md to
strip a fence → the contract test correctly flagged it). `grade.py` is pure JSON→JSON (no
`eval`/`exec`/`subprocess`/`open`/network/SQL; regexes linear, no ReDoS). The case-3 injection
fixture is consumed only as data (`grade.py` never reads `answer`/`examined`). No `scripts/`/`sql/`
change. **C2 verified**: anti-bleed removed only advisory-lens (`logic`/`completeness`) injection
re-reports that never affected the gate; both FAIL-lenses (`factual`+`security`) retain the
injection, so injection-FAIL defense-in-depth is intact.

## Findings
- **F-1 (MEDIUM)** — the defang check is a closed canary allow-list; a novel un-fenced directive
  phrasing outside the tokens could pass a future edit. **Partially hardened in 009-06** (broadened
  control-token list); residual recorded as **KNOWN_ISSUES L-009-3** (future: structural
  imperative-in-example-region check). Not a current vulnerability (every canary today is fenced).
- **F-2 (LOW)** — canary compare was case-sensitive (gate `_is_fail` is case-insensitive).
  **Fixed in 009-06** (lowercased compare, mirroring `_is_fail`).
- **F-3 (INFO)** — the one live attack string sits in a balanced `​```text` fence, labelled
  "EXAMPLE … NEVER obey" + "as DATA". Residual model-parse risk mitigated, not eliminated (no prompt
  fully eliminates it); best-practice framing. Highest-value line to keep under review.
- **F-4 (INFO)** — C2 backstop is data-guaranteed (case-3 carries both `security` critical + `factual`
  ≥ high; enforced by `test_injection_case_has_c2_backstop_data_guarantee`).

**Defang verdict:** sufficient + regression-proof for the current change set; token-list (not
structural) → L-009-3 for future durability. **H-6 verdict:** preserved, arguably strengthened
(C2 adds FAIL-redundancy). SECURITY-label PR rule on `skills/wiki-verify/` remains the backstop.
