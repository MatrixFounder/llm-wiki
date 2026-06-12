# RED structural record — bead 029-00 (skeleton, pre-content)

Date: 2026-06-12 · Skill: `skills/obsidian-cli/` · State: skeleton (intentional)

Structural checklist applied manually (skill-validator is an external/framework
skill — plan-review NIT-2; same checklist items):

| # | Check | Verdict | Finding |
|---|-------|---------|---------|
| 1 | Frontmatter parses (name/tier/version) | PASS | `name: obsidian-cli`, `tier: 2`, `version: 0.1` |
| 2 | `description:` quality (triggers, routing, non-shadowing) | **FAIL (RED)** | placeholder `TODO-029-02` — no triggers, no NOT-for routing |
| 3 | SKILL.md sections non-empty | **FAIL (RED)** | all 8 sections are `<!-- TODO 029-02 -->` |
| 4 | References present & versioned | **FAIL (RED)** | command-reference: version stamp TODO, all sections TODO; recipes: 8 headers, zero bodies |
| 5 | Eval suite present | **FAIL (RED)** | `evals/evals.json` absent (authored in 029-01); README rubric TODO |
| 6 | No scripts / no executable code in skill | PASS | text-only tree, nothing executable |
| 7 | Vendor symlinks resolve | PASS | `.claude/skills/obsidian-cli` + `.agent/skills/obsidian-cli` → `../../skills/obsidian-cli` |

RED summary: 4 structural failures — exactly the content the Phase-2 beads
(029-01..04) must supply. The eval expectations (029-01) are unsatisfiable against
this skeleton by construction: no routing/safety text exists for E-01..E-14 to hold.

GREEN criteria: checks 2–5 flip in 029-02 (description+sections), 029-03
(reference), 029-04 (recipes), 029-01/05 (evals authored / run PASS).
