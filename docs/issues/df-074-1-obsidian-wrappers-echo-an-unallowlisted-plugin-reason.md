---
id: DF-074-1
type: known-issue
status: fixed
opened_at: 2026-08-10
fixed_at: 2026-08-10
category: security
severity: SEV-3
slug: df-074-1-obsidian-wrappers-echo-an-unallowlisted-plugin-reason
---

# The `obsidian-*` wrappers allow-list the plugin's failure *exit code* and pass its failure *string* straight through — the trust boundary is applied to one half of the same value

- **Symptom**: `skills/obsidian-cli/scripts/obsidian_selection.py:421` and `:594`, and
  `obsidian_context.py:167-171`:

  ```python
  reason = str(result.get("reason", "unknown"))
  return {"ok": False, "mode": "read", "reason": reason}, _REASON_EXIT.get(reason, EXIT_APP_NOT_RUNNING)
  ```

  `result` is parsed from the **unsigned** `.obsidian/agent-result.json` written by the
  `agent-bridge` plugin. The **exit code** is allow-listed through `_REASON_EXIT` (an unknown
  reason fails closed to `EXIT_APP_NOT_RUNNING`). The **string** is not: arbitrary
  attacker-chosen text reaches the wrapper's stdout envelope and therefore the agent's context.

- **★ The asymmetry is the finding, and it is inside one file.**
  `obsidian_context.py:179-191` spends nine lines arguing that the *success* payload must be an
  **allow-list, not a deny-list** — «the wrapper is the trust boundary between the UNSIGNED
  `agent-context.json` and the agent» — and the *failure* path one branch earlier applies
  neither. `obsidian_selection.py`'s own module header already models a **hostile local writer**
  (that is the stated reason for its `RecursionError` clause), so this adversary is in scope for
  these files by their own threat model, not by an imported one.

- **Severity SEV-3, stated honestly.** Exploitation needs local write access to `.obsidian/` or a
  hostile plugin build — i.e. an attacker who already has the user's filesystem. The value is
  LLM01 indirect-prompt-injection surface (CWE-117), not privilege escalation. What makes it
  worth filing rather than shrugging at is that the *mitigation already exists eight lines away*
  and was simply not applied to this branch.

- **Fix shape** (not done here): `reason = reason if reason in _REASON_EXIT else "unknown"` at all
  three sites — the exit-code mapping already treats an unknown reason as fail-closed, so this
  only makes the string agree with the number. Consider lifting the guard into the shared module
  the three wrappers already import from, per the TASK 071 rule that these wrappers **import**
  their guards rather than re-porting them.

- **Found by**: `critic-security` during the `/vdd-multi` pass on TASK 074 (F4). Out of that
  task's diff — these files were not touched — which is why it is an issue and not a fix. It
  surfaced because TASK 074's new gate **pins the `obsidian-*` trio as a static blind spot**, and
  the reviewer was asked to check whether the blind spot was hiding anything. It was.

---

## Resolution — TASK 074 (same session), 2026-08-10

**Fixed at all three sites.** `obsidian_selection.safe_reason()` collapses any reason that is not
a known `_REASON_EXIT` rung to `"unknown"` — the same conclusion the exit-code mapping already
draws — so the number and the string can no longer disagree. `obsidian_selection.py` (read + apply)
uses it directly; `obsidian_context.py` calls `_sel.safe_reason`, **importing** the guard rather
than re-porting it (the TASK 071 rule).

★ **Two existing tests asserted the defect.** `test_read_unknown_plugin_reason_fails_closed_exit_4`
in both suites pinned `out["reason"] == "some-unknown-reason"` — i.e. it pinned the verbatim echo.
They were written for the *exit code* property and the string equality rode along unexamined.
Both now assert the stronger property: exit 4 **and** `reason == "unknown"` **and** an
injection-shaped canary does not appear anywhere in stdout. New unit
`test_safe_reason_allowlists_against_the_same_ladder_as_the_exit_code` walks every documented rung
so a real one can never be collapsed by accident.

**Fixed because the operator said so** — this was originally filed rather than folded in, on the
grounds that it sits outside TASK 074's diff. That was the wrong call for a one-line guard whose
mitigation already existed eight lines away.
