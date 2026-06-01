# PLAN — TASK 011 (`wiki-verify` eval-v4, deep multi-hop)

> Decomposes [TASK.md](./TASK.md) (RTM 11.1–11.8) into Stub-First beads. **Zero
> code/schema/prompt change** — fixtures + one new test module + a recorded measurement. v4 is
> a separate file, so the committed v1/v2/v3 reproducibility pins stay byte-identical
> ("old benchmarks don't degrade" by construction).

## Stub-First strategy (eval set)

The "stub" is the case skeleton + the well-formedness test. A **self-validating Python builder**
asserts — before writing `evals-v4.json` — that every span ⊂ `answer+bodies`, every broken-link
span is **absent from all source bodies** (the fabrication property), `(defect_id,lens)` unique,
and `_is_fail==verdict`. Then the test pins it (RED→GREEN). Only then run the (LLM) 4-critic
measurement and pin its reproducibility.

## Beads

| Bead | Title | RTM | Outputs |
|---|---|---|---|
| **011-01** | 3 chains + ~10 seeded cases | 11.1–11.4 | `evals-v4.json` (seeded portion) via self-validating builder |
| **011-02** | well-formedness + deep-chain test | 11.6 | `tests/test_wiki_verify_v4.py` (mirror v3 + `test_v4_exercises_deep_chains` + `test_v4_has_broken_middle_hop_group`) |
| **011-03** | ~3 natural traversal cases | 11.5 | synth organic answers → dual-blind consensus label → `evals-v4.json` |
| **011-04** | orchestrator-run measurement | 11.7a | `reports/v4/shipped-run-outputs.json` + `shipped-grading.json` |
| **011-05** | repro pin + report | 11.6c, 11.7b-c | repro-pin test + `reports/v4/benchmark-v4.md` (broken-middle-hop recall headline) |
| **011-06** | docs + regression verification | 11.8 | README v4 section; full `pytest tests/` + `mypy`; v1/v2/v3 pins byte-identical |

## Chains (the source data — designed in detail)

| chain | domain | hops | traversal |
|---|---|---|---|
| 1 | ip-provenance | 5 | Helios→Vega→Polaris patent→Aurora algo→Borealis line→Tundra appliance |
| 2 | estuary-ecology | 5 | silt→diatoms→krill→glass smelt→tern→Skarn Islet colony |
| 3 | build-dependency | 4 | Cobalt→Ferrite→Garnet→Onyx (CVE-2025-0440) |

Each hop carries a uniqueness clause ("sole/only/exclusively/no … of its own") so a broken link
is unambiguously unsupported. Chain-3 transitive-CVE = `factual` (NOT `security`); guard the
clean case with a `security` forbidden-finding to measure any CVE-language over-fire.

Case matrix: 3 clean-traversal PASS · 4 broken-middle-hop FAIL (hop2/hop3/hop4) · 2 wrong-terminus
FAIL · 1 unsupported-leap FAIL · ~3 natural PASS.

## Regression safety
1. **Adding v4 is non-regressive by construction** — separate file; `grade.py` + committed
   v1/v2/v3 run-outputs untouched → their pins byte-identical; the new test exposes a coverage
   gap, it changes no production behavior.
2. **A future endpoint-bias prompt fix is gated separately** — full-corpus v1+v2+v3+v4
   no-degradation A/B (the D-010-1/D-010-2 protocol), its own SECURITY PR.
3. **No gaming** — seeded ground-truth is mechanical (broken link absent from all sources);
   natural is consensus-labeled blind to the prompt; critics blind to `expected_findings`.

## Out of scope
- Prompt fixes (deferred, gated); front 2b (reliability conflict); merge to `main` (user-confirmed).
