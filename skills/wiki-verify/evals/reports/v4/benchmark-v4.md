# `wiki-verify` prompt — BENCHMARK v4 (deep multi-hop extension, 13 cases)

**TASK 011 — coverage extension (front 2a).** `evals-v4.json` exercises the **4–5-source
dependency-chain** traversal path that v3 never tested (v3's max chain was 3 sources, mostly
2-hop joins), and the signature **broken-middle-hop** failure: an answer with **correct
endpoints but a fabricated middle link** → unsupported conclusion. The diagnostic question:
**does the shipped 4-critic prompt verify every hop, or only the endpoints?**

- **Cases:** 13 = **10 seeded** (objective ground-truth) + **3 natural** (organic `wiki-query`
  traversals, consensus of 2 blind labelers). 3 chains, 3 fictional domains.
- **Run:** shipped `SKILL.md` v1.2 (git blob `f38799aa`); `evals-v4.json` sha256 `ad77a3af…`;
  run date 2026-06-01. `4 × 13 = 52` blind critic sub-agents (critics never see
  `expected_findings`); raw outputs committed (`reports/v4/shipped-run-outputs.json`) →
  reproducible via `grade.py` (`tests/test_wiki_verify_v4.py::test_v4_shipped_grading_reproducible`).

## The chains (source data)
| chain | domain | hops | traversal |
|---|---|---|---|
| 1 | ip-provenance | 5 | Helios→Vega→Polaris patent→Aurora algo→Borealis line→Tundra appliance |
| 2 | estuary-ecology | 5 | silt→diatoms→krill→glass smelt→tern→Skarn Islet colony |
| 3 | build-dependency | 4 | Cobalt→Ferrite→Garnet→Onyx (CVE-2025-0440) |

Each hop carries a **uniqueness clause** ("the *sole* method", "graze *exclusively* … *eat
nothing else*", "*no* arithmetic of its own", "the *only* release affected") so a broken link
is unambiguously unsupported and ground-truth stays objective. The **broken-middle-hop** cases
break **different positions** (hop2/hop3/hop4) and substitute a fabricated entity absent from
*every* source (Zephyr, Cirrus, a diatom→smelt collapse, a Ferrite→Onyx shortcut). Chain-3's
transitive CVE is treated as a **`factual`** matter (a fabricated dependency edge / CVE id),
**not** `security` — and the clean case carries a `security` forbidden-finding to catch any
CVE-language over-fire.

## Results — shipped prompt vs deep chains

| group | n | recall | verdict-match | false-pos | unsanctioned purity-viol |
|---|---|---|---|---|---|
| clean-traversal (PASS, FP-guard) | 3 | — | 1.000 | 0 | 0 |
| **broken-middle-hop** (FAIL) | 4 | **1.000** | 1.000 | 0 | 2 |
| wrong-terminus (FAIL) | 2 | 1.000 | 1.000 | 0 | 1 |
| unsupported-leap (FAIL) | 1 | 1.000 | 1.000 | 0 | 0 |
| natural (PASS) | 3 | — | 1.000 | 0 | 0 |
| **OVERALL** | 13 | **1.000** | **1.000** | **0** | **3** |

severity-match 1.000.

## Headline — NO endpoint-bias

**broken-middle-hop recall = 1.000 = wrong-terminus recall.** The shipped prompt catches a
**fabricated interior link** (whose endpoints look correct) just as reliably as a wrong final
entity — at `factual`/high in every case. There is **no deep-chain blind spot**: the verifier
checks every hop, not only the endpoints. The critic notes confirm it reasons about the chain
explicitly (e.g. case 60: *"fabricates a direct diatom→smelt feeding relationship … dropping
the krill trophic level"*; case 57: *"substitutes a fabricated product-line name ('Cirrus')
for the actual one ('Borealis') in the ownership chain"*).

**Zero false-positives** on the 3 clean traversals and 3 natural organic traversals — the
prompt does not "panic on a long chain", and the `security` lens did **not** over-fire on the
CVE language (the Chain-3 FP-guard held).

## Tracked finding — carry-over completeness-bleed (3 violations)

`unsanctioned_purity_violations = 3` on cases 60, 63, 64 (`completeness` re-reports the
`factual` broken-link/terminus defect as an "omitted true link"). This is the **same
omission-conflation class as D-010-2** (KNOWN_ISSUES) — lens-purity NOISE, not a recall/verdict
defect (the gate is sound: recall 1.0, verdict 1.0, FP 0). It is the expected residual on
inversion/fabrication-type FAIL cases and is **not re-fixed here** (D-010-2 mitigated it in
expectation; a deterministic fix is the deferred grader change). Recorded as carry-over.

## Non-regression
v4 is a **separate file**; `grade.py` and the committed v1/v2/v3 run-outputs are **untouched**,
so the v1/v2/v3 reproducibility pins stay **byte-identical** (verified: 33 v1/v2/v3 + grader
tests green; empty diff vs `main` on `grade.py`/`SKILL.md`/`scripts/`/old datasets). The shipped
prompt is **not modified** — v4 is dataset + measurement only. (Had the measurement shown
endpoint-bias, a prompt fix would have run a full-corpus v1+v2+v3+v4 no-degradation A/B; it
showed none, so no fix is warranted.)

## Reproducibility
`grade_run(evals-v4.json, shipped-run-outputs.json) == shipped-grading.json`, pinned by
`tests/test_wiki_verify_v4.py`.
