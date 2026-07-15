# 7. Security

> Part of [docs/ARCHITECTURE.md](../ARCHITECTURE.md).


### 7.1. Authentication and Authorization

**Single-user personal tool. No auth.**

- Skills исполняются под user-account, читают/пишут within vault permissions.
- `ANTHROPIC_API_KEY` хранится в `~/.config/wiki-mcp/keys.env` (env file, **никогда** не commit'ится; `.gitignore`).
- Future Epic 6: Gmail OAuth + Telegram MTProto session keys тоже в `~/.config/wiki-mcp/`.

### 7.2. Data Protection

- **At rest**: Markdown в iCloud Obsidian — encrypted iCloud sync. SQLite — local FS, **не** в iCloud (R-03). No additional encryption (vault уже под user permissions).
- **In transit**: HTTPS для всех external API calls (Anthropic).
- **PII**: `wiki.research.private_concepts` + `private_tags: [confidential]` — fail-fast в research/external-share. MVP не имеет research/external-share, но schema готова.
- **Policy-before-model**: [ADR-009](../adr/ADR-009-policy-before-model.md) / ROADMAP R-16 / TASK 049 — опциональный `classification:` + `--audience` retrieval-scope гейт (SQL-предикат ДО попадания контента в model-context/envelope). Least-privilege для model-инвокаций и subagent'ов, НЕ multi-user authZ (см. Out-of-scope ниже + §7.6).
- **Backups**: Vault уже git-versionable (рекомендация); SQLite — derivative, всегда rebuildable. **Скиллы не делают бэкапы** (per TASK §22 v2).

### 7.3. Attack Protection (OWASP-aligned)

- **A03 Injection**:
  - **SQL Injection**: все queries через parameterized statements (`?` для SQLite, `%s` для Postgres). Test: ingest файла с frontmatter `title: "'; DROP TABLE pages--"` → table остаётся.
  - **Command Injection**: `wiki-source-transcript` использует `subprocess.run([...], shell=False)` — argv list, не shell-string.
- **A01 Broken Access Control**:
  - **Path Traversal**: `wiki-source-manual` validates `os.path.realpath(source).startswith(os.path.realpath(vault_root))`. Test: `--source ../../../etc/passwd` → fail-fast.
- **A04 Insecure Design**:
  - SQLite вне iCloud (R-03) — phys-design защита от sync-corruption.
- **A05 Security Misconfiguration**:
  - JSON Schema validation для config до запуска любого skill (R-01.3).
  - Fail-fast если `wiki:` блок отсутствует в `CLAUDE.md`.
- **ReDoS / Availability (TASK 017 — R-X1-REDOS-RT)**:
  - **Threat**: an operator-custom layout regex (`ref_extraction[].regex` / `project_pattern`)
    that backtracks catastrophically on long file *content* can hang `wiki-reindex` (single-
    user DoS / stuck maintenance). Built-in layout patterns are pre-vetted.
  - **Control (defense-in-depth, two layers)**: (1) load-time `_redos_budget_check` rejects
    obviously-catastrophic operator regex at config-load (exit 6) — a short-payload heuristic;
    (2) a **runtime per-file `timeout=` deadline** via the `regex` engine on operator-custom
    patterns (`WIKI_REDOS_BUDGET_S`, default 2.0 s) → degrades to skip-file-with-WARN, never
    hangs. Verified: builtin `TimeoutError` fires at the deadline even on a 100 KB single line
    (stdlib `re` cannot be interrupted — GIL-held C call). See §3.5 "Runtime ReDoS deadline".
  - **CWE-117/209**: skip/WARN reasons name the file, never echo the offending pattern or body.
- **A06 Vulnerable & Outdated Components**: TASK 017 adds **one** runtime dependency — `regex`
  (PyPI, pinned floor `>=2024.0`) — for the control above: a single, widely-used, actively-
  maintained package, no transitive bloat; `types-regex` for the type gate. (Pre-017 the tool
  was stdlib + frontmatter/yaml/slugify/jsonschema only.)
- **A08 Software & Data Integrity**:
  - `pages.file_hash` (sha256) для change detection.
  - `vault_metadata.schema_version` для migration tracking.
- **A09 Logging Failures**:
  - `log.md` append-only с monthly rotation. Не редактируется автоматически.
- **A10 SSRF**: `wiki-source-light` отправляет только в Anthropic API (hard-coded host). Не принимает user-supplied URL.

**Out-of-scope для MVP** (per TASK):
- Multi-user RBAC. _(Единственный запланированный шаг в эту сторону —
  single-operator retrieval scoping, [ADR-009](../adr/ADR-009-policy-before-model.md)
  Proposed / ROADMAP R-16: скоупит что видит **модель**, не пользователь;
  настоящий multi-user authZ остаётся trigger-gated → Postgres, ROADMAP P3.)_
- Audit logs beyond `log.md`. _(Read-side полнота аудита — ROADMAP R-17.)_
- Encryption at rest (vault encryption — responsibility пользователя).

### 7.4. Vendoring Policy

> **⚠️ Superseded (TASK 047).** The vendored `scripts/wiki_ingest/` module, its `wiki-enrich`
> on-ramp, and the `scripts/sync_wiki_ingest.sh` snapshot-sync were **retired** — the converged
> `wiki-import` engine (TASK 046) replaced them, so there is no longer a vendored copy to sync or
> a drift surface to guard. The policy below is preserved as the historical record of Decision-11/12;
> it no longer describes a live subsystem.

Snapshot-based vendoring is used for the `wiki_ingest` Python module to eliminate the external PATH dependency (Decision-11). Key policy points:

**Rationale for snapshot over live link:** A snapshot copy (vs git-submodule or pip dependency) minimises install friction for end-users (target: single-step `pip install obsidian-llm-wiki`), avoids network fetches at runtime, and gives the repo a stable import surface. The trade-off is manual sync, which is bounded and operator-controlled.

**Sync strategy:** `bash scripts/sync_wiki_ingest.sh` (rsync from configurable upstream path). The script is idempotent: re-running immediately produces "no changes". Supports `--dry-run` (no mutations) and `--accept-local-divergence` (bypass hash abort for documented patches).

**Drift detection mechanism:** `VENDORED_FROM.md::file_hashes` records SHA256 content hashes of all committed `*.py` files at sync time. Pre-sync, the script recomputes hashes and aborts with a per-file diff if any hash diverges from the recorded value and is not covered by a `local_patches` entry. This mechanism works regardless of whether the operator commits between syncs and does not assume the source path is a git checkout. See §1.5.7 for full details.

**Upstream-first fix policy (Decision-12):** All bug fixes go to `Universal-skills/skills/wiki-ingest` first, then sync down. Local divergences in the vendored copy are prohibited except for documented `local_patches` (primarily `mypy --strict` type-annotation fixups — R-50). Each local patch carries a `# VENDORED-PATCH:` comment and is listed in `VENDORED_FROM.md::local_patches` so the sync script can warn before overwriting.

**Third-party notices:** Covered in `THIRD_PARTY_NOTICES.md` (R-55). Both repos are operator-owned; no open-source licensing friction today. The notices file is maintained for clean posture in anticipation of future publication (TASK 005 — PyPI).

---


## 7.5. Sync Dispatcher (`wiki-sync`, TASK 018 / R-11)

`wiki-sync` widens the *input surface* (it discovers heterogeneous files and drives
conversion), so its security posture is explicit:

- **Path-traversal (SEC-A3/A6 refinement):** discovered paths are validated inside
  the vault; the symlink refusal covers both the **target file AND its directories**
  (`O_NOFOLLOW`, not just the leaf). The converted markdown is written atomically
  (`tempfile + os.replace`) inside the vault — note `validate_inside_vault(strict=True)`
  cannot resolve a *not-yet-existing* target, so the containment guard is on the
  **existing `_raw/` parent dir** (+ symlink refusal), not the unborn target path.
- **Staging-name collision (SEC-A4/EC-5; + RG-5/SEC-N1):** the staged target is the
  **collision-safe** `_raw/.staging/<slug(stem)>-<ext>.md` — in the **non-walked**
  `.staging/` subdir (so it is never re-ingested, RG-1/W-3) and disambiguated by
  extension (same-stem `.docx`/`.pdf` never share a target). Before writing, if a
  target exists with **different** content the executor **refuses to overwrite** and
  emits a `staging-collision` reason — never a silent `os.replace`. (Modelled on
  `register_summary`'s refuse-overwrite posture, which refuses on *existence* absent
  `--force`; here refined to compare **content** so an identical re-stage is
  idempotent.) Planning must define the **empty-slug fallback** (a punctuation-/
  whitespace-only stem slugifies to `''`): substitute a path-derived disambiguator
  `_raw/.staging/sync-<sha8(vault-relative-source-path)>-<ext>.md` (SEC-N1).
- **Untrusted content (H-6 — binding; SEC-A1 fix):** raw sources and converted
  markdown are **data, not instructions**. The deterministic `scan` never interprets
  file *content* as directives. ⚠️ The **first** LLM stage on the ingest chain is
  `summarizing-meetings`, which has **no** built-in H-6 banner (the existing banners
  are on the second-stage `wiki-extract-concepts`/`wiki-query` only) — so the executor
  MUST fence each raw/converted body with a sentinel **before** `summarizing-meetings`,
  not only at the extractor. File content is **never executed**.
- **Write-side injection canary (H-6 item (c), 2026-07-15):** ingress fencing (above) is
  advice to the model; the canary is a **mechanism**. Both typed-knowledge extraction rails
  (`wiki-extract-concepts`, `wiki-extract-decisions`) run the shared
  `_common.scan_injection_canaries` over the **model-authored** candidate fields
  (`name`/`definition`, `title`/`body`) and REFUSE — `INJECTION_CANARY`, exit 4, **zero
  files** — a chat-template control token (`<|…|>`/`[INST]`/`<<SYS>>`), a **line-leading**
  all-caps `SYSTEM:` role directive, or an `ignore`/`disregard previous instructions`-style
  override the model has **parroted** out of a hostile body. Refuse-don't-escape: a laundered
  marker never reaches a clean `_concepts/`/typed page a later scoped synthesis would read back
  as an instruction. ⚠️ **Precision over recall, deliberately** (this is defense-in-depth, not
  the primary control): the imperative family is `ignore`/`disregard` + an injection-object
  noun ONLY — `override`/`forget` + `context`/`rule` are ordinary CS/ML definitions
  (`override the previous rule`, an `LSTM forget gate`) and were dropped after a **measured
  7/8 false-positive rate** on a technical-definition set (vdd-adversarial 2026-07-15); the
  role directive is **line-anchored** so a mid-sentence all-caps role word passes. The rarer
  phrasings those exemptions let through are covered by the structural-token canaries +
  classification + egress-sanitisation, not by inflating this family into a live FP source.
  ★ The verbatim `source_quote` is **deliberately exempt** — it is proven-in-body source
  content (a legitimate security article quotes these markers), is escaped inert on egress by
  `sanitize_markdown_text`, and `_raw/` is already classification-quarantined (item (d)); a
  quote scan would refuse the source's own evidence — the gate an operator routes around.
  Value never echoed (CWE-117). This closes the last concrete H-6 fix-plan item (issue →
  `mitigated`; the residual injection class is architecturally inherent to LLM01).
- **Skill-contract integrity (H-5 item (a), TASK 067, 2026-07-15):** the H-6 canary refuses an
  injection copied out of an untrusted SOURCE; H-5 detects tampering with the REASONING CONTRACT
  ITSELF — a `skills/*/SKILL.md` the orchestrator loads VERBATIM (Decision-17: the prompt is
  Markdown, not Python, so pip never pins its bytes). The banner was a **comment**; this is a
  **mechanism**, applied across the whole repo-owned loaded-verbatim surface (the hole is identical on
  every REASON/safety contract — the unenumerated-surface lens). ★ **Enrolment cross-checked, not
  single-source** — the adversarial review found marker-ONLY enrolment missed **`obsidian-cli`**, a
  verbatim safety-tier model (T3 `eval`/RCE ban) that `skills/.AGENTS.md` *already* designated
  same-class: a code-exec stored-injection hole leaving every gate green. Now TWO enrolments that must
  agree — (1) the `SECURITY-SENSITIVE` marker grep (recursive `skills/**/SKILL.md`, shared by re-pin +
  test) → manifest; (2) `_DESIGNATED_VERBATIM_CONTRACTS`, a positive allow-list asserted all-pinned —
  a `Skill({skill:X})` load-site test; and — cycle-3 — a completeness test grepping **ALL** skills
  markdown so a marker'd file in ANY location is pinned-or-exempt (enrolment is file-shape-independent,
  not scoped to `SKILL.md`). **Seven** SHA-256-pinned in `config/skill-integrity.sha256`: 5 `SKILL.md`
  (`concept-extraction`, `decision-extraction`, `wiki-query-synthesis`, `wiki-verify`, **`obsidian-cli`**)
  **plus 2 `references/*.md`** (cycle-2 review MAJOR — verbatim contract content lives there too):
  `obsidian-cli/references/command-reference.md` (per-command tier table; a T3→T1 re-tag the SKILL.md
  model doesn't backstop) and `wiki-import/references/reason-contract.md` (the **sole home of the H-6
  injection fence** for the import/sync REASON step). `wiki-verify-multi/SKILL.md` + `skills/.AGENTS.md`
  **exempt by name+reason**. Stated residuals (exhaustive-sweep-verified): `summarizing-meetings`
  (**vendored** → Vendoring Policy §7.4), `recipes.md` (playbooks), operator CLI-reference SKILL.md. ★ **Runtime:** each
  rail's `prepare` embeds a value-free `integrity` block (`_common.verify_skill_integrity` — path +
  hex hashes only, CWE-117/209); every workflow's load-skill step **STOPs before loading** on
  `status != "ok"`, and `WIKI_STRICT_SKILL_INTEGRITY=1` makes `prepare` **refuse** (exit 2
  `SKILL_INTEGRITY_DRIFT`) — the check sits BEFORE the load, so a drift STOPs the orchestrator before
  the tampered prompt is ever in context. ★ **CI:** `tests/test_h5_skill_integrity.py` goes RED on any
  un-re-pinned edit — the mechanical, vendor-neutral delivery of fix-plan item (d)'s "flag the change
  for SECURITY review," without a git hook. Re-pin an approved edit with `scripts/pin_skill_integrity.py
  --write` (a reviewable manifest diff). ⚠️ **Honest residual (stated, not hidden):** this does NOT
  stop a malicious maintainer who edits a contract AND re-pins in the same commit — that is
  branch-protection / CODEOWNERS on the manifest, an operator concern out of runtime scope; it makes
  silent tampering impossible without a reviewable diff + a red test, and catches on-disk
  drift/corruption/non-committer tampering at invocation. Options (b) signing / (c) prompt-into-Python
  carry the *same* maintainer residual at more weight — deferred (TASK 067 §7).
- **Resource bounds + YAML anchor-bomb (SEC-A5 corrected — SEC-N3, the binding fix):**
  binaries are skipped by extension *before* any read; a `.md` over
  `WIKI_SYNC_MD_MAX_BYTES` (8 MiB) is **skipped (`oversize-source`) before
  `read_text`** — the one unbounded-RAM lever in `scan`, now bounded (vdd-multi
  SEC-MED); the convert/text hash read is chunk-streamed (bounded RAM). A
  symlinked `.wiki/sync.yaml` is refused (`O_NOFOLLOW`). ⚠️ **`yaml.safe_load`
  does NOT defang a billion-laughs/anchor-bomb** —
  it only blocks arbitrary-object construction (`!!python/object`), and **still
  expands aliases/anchors** (a 232-byte bomb expands to ~531 k nodes; a sub-256 KiB
  bomb reaches 10⁸). So the `.wiki/sync.yaml` defense is: (1) a **256 KiB input
  size-cap** (`stat().st_size` before read) — necessary but **not sufficient alone**;
  (2) **forbid YAML anchors/aliases entirely** via a custom `SafeLoader` subclass that
  raises on an anchor/alias node (the sync config is a flat dict of glob strings —
  anchors have no legitimate use), which is the actual anchor-bomb bound. One
  oversize/unconvertible/`needs-ocr`/`unmappable-type` file is flagged, never crashes
  the batch (per-file isolation).
- **Config injection:** `.wiki/sync.yaml` is strict-schema-validated against
  `config/sync-config.schema.yaml` (a misspelled key is a load error, not a silent
  skip); `zones`/`exclude` are **path globs**, not regexes — no
  operator-supplied-regex ReDoS surface is introduced (unlike the layout engine's
  `ref_extraction`/`project_pattern`, which keep their TASK-012/017 ReDoS guards).
- **Concurrency (META-2 specified — SEC-N4):** the executor takes a **per-vault
  advisory `flock` on `<vault>/.wiki/sync.lock`** with **`LOCK_EX | LOCK_NB`** — if
  already held, `wiki-sync` exits `2` `SYNC_IN_PROGRESS` (it does **not** block for
  the multi-minute run). The lock is held on an open fd for the executor's lifetime
  and auto-released on process exit (no stale-file recovery needed — `flock` is
  fd-scoped, unlike the short-lived per-append `wiki-append-log` lock, which is a
  *different* profile and is **not** cited as the precedent for lifetime). It guards
  `wiki-sync` runs **against each other only**; unrelated writers (`wiki-append-log`,
  `wiki-query`) take their own short locks and are unaffected (they never acquire
  `sync.lock`). Operator edits *during* a run remain the documented single-actor
  precondition (a file changed mid-walk is detected by the next run's hash).
- **No new authZ surface:** single-user, file-permission trust scope unchanged;
  `wiki-sync` adds no network or credential surface (no `import anthropic`).

---

## 7.6. Policy-before-model retrieval scoping (TASK 049 / ADR-009 / R-16)

The classification layer adds a **capability-scoping control for model invocations**,
not an authZ boundary. Its security contract:

- **Threat model addressed:** (1) accidental exposure of sensitive vault content into a
  model context / third-party API during routine RAG — especially subagent/critic
  contexts run least-privilege (`wiki-verify-multi --audience`); (2) leakage into
  **durable Class-A artifacts** (filed `_queries/*.md` answers, verification pages)
  that get committed/synced/read downstream — blocked mechanically by the pre-LIMIT SQL
  filter + the existing `CITATION_NOT_RETRIEVED` grounding gate; (3) cross-vault bleed
  under `--vaults all` (home-vault ladder applies; foreign labels fail closed); (4) H-6
  blast-radius reduction — `wiki-import --classification restricted` quarantines a
  hostile `_raw/` capture from every lower-audience synthesis (the KNOWN_ISSUES H-6
  "`_raw/` second-class" mitigation, implemented).
- **Explicit NON-goals (never claim otherwise):** a malicious local operator or
  orchestrator (they own the files and can open the SQLite DB directly — the DB
  contains the content), tampered CLIs, or an operator passing the highest audience.
  The profile is **self-declared** (flag > vault `default_audience` > OFF). Real
  multi-user authZ stays trigger-gated to the Postgres/multi-tenant migration
  (ROADMAP P3 / R-9 trigger).
- **Enforcement is deterministic, not prompt-layer:** one bound SQL predicate in
  `search_pages` (pre-LIMIT, all three query shapes, all values bound — the no-f-string
  posture holds) + per-page gates on the two `get_page` bypass paths
  (`_follow_edges`, `_gather_examined`). Unknown level strings are excluded
  (fail-closed `IN`). No level/label VALUE is ever echoed in an error (CWE-209/117);
  `wiki-verify-multi` reports excluded cites as a **count only**.
- **H-6 interplay:** policy is an *ingress-to-context* gate, orthogonal to and
  compounding the prompt-armor + egress sanitizers — content that IS allowed through
  remains untrusted data; `sanitize_markdown_text` and the fenced-sentinel rules are
  unchanged.
- **Defense-in-depth (documentation-level, vendor-specific):** operators MAY add
  `Read`-deny globs for restricted folders in `templates/vault.claude-settings.json` /
  `vault.pi-permissions.json` to also block an orchestrator's direct file reads on
  harnesses that support permissions — documented as belt-and-braces, never the
  boundary.

**TASK 050 addendum — the derived trust tier is ADVISORY, not an authorization
boundary.** `--min-trust verified` keys on inbound `verifies` refs, which are minted by
any page routed to `type: verification` (normally only `wiki-verify-multi apply` writes
those); the derivation validates neither the VERIFIER's own tier/classification nor its
project (Q-050-1). Within the §7.6 trust scope this means: (i) content that can author a
`type: verification` page (e.g. an H-6 prompt-injection subverting an import REASON
step) can confer `verified` — the tier raises the bar, it does not gate writes; (ii) a
page verified only by a RESTRICTED verification page still shows `verified` to a lower
audience — a 1-bit existence signal, no content; (iii) a page citing an external source
under a frontmatter key the derivation does not recognise evades the `external` tier.
These are accepted advisory-tier imprecision, consistent with the operator-trusted
boundary; treat `trust` as a prompt-side signal and `--min-trust` as hygiene, never as
access control (that is `--audience`'s job).

**TASK 061 / R-061-3 addendum — the `Source:` limb of (iii) is CLOSED, and its stated
justification was already false.** Pre-061 this paragraph excused the `Source:` evasion
on the grounds that *"the framework's own writers use the canonical keys and the `_raw/`
path anchor."* Both halves were wrong, and the live vault said so:

- **13 pages carried `Source:` with an external URL AND derived `internal`** — the trust
  layer failed **OPEN**. They are clipper- and hand-authored pages, i.e. exactly the
  population the excuse assumed away: "our own writers use canonical keys" is not a
  property of a vault that also holds content the framework did not write.
- **The `_raw/` path anchor is not an anchor at all in retrieval** (R-061-7): every
  built-in layout excludes `**/_raw/**` from the index, so **0 of 3267 live pages** are
  external-by-path. It backstops direct upserts, nothing more.

> **The `Source:` census, reconciled** (061 VDD iteration-2 / LOW-2). This doc said
> **18**, `policy.py` said **19**, the tests said **18**, and nothing executable gated
> any of them. Both numbers were true **of different nouns**, and *neither was the number
> a security claim may cite*: **19** pages carry the KEY; **18** of those carry an
> `http(s)` scalar under it; **13** of those actually derived `internal` (the other 5 were
> already `external` via a canonical `source`/`url`/`URL` key). The fail-open count is
> **13** — and the arithmetic below always said so: pre-061 external = **707**, and
> 707 + 13 = **720**, + 17 = **737**. It never closed on 18. Leaving an unreconciled
> 18-vs-19 next to a headline correction about *counting the wrong noun* was the same
> disease, third recurrence. The number now lives in ONE place
> (`policy.EXTERNAL_PROVENANCE_KEYS`) **with the query beside it**, re-runnable
> read-only against the live vault (`mode=ro` — never write to it):
>
> ```sql
> -- 13; drop the NOT EXISTS -> 18; drop the type/LIKE guard too -> 19
> SELECT COUNT(*) FROM pages p WHERE EXISTS (
>   SELECT 1 FROM json_each(p.frontmatter_json) je
>    WHERE je.key = 'Source' AND je.type = 'text'
>      AND (je.value LIKE 'http://%' OR je.value LIKE 'https://%'))
>   AND NOT EXISTS (
>   SELECT 1 FROM json_each(p.frontmatter_json) je2
>    WHERE je2.key IN ('source','url','URL') AND je2.type = 'text'
>      AND (je2.value LIKE 'http://%' OR je2.value LIKE 'https://%'));
> ```

`policy.EXTERNAL_PROVENANCE_KEYS` now enumerates the **case variants** *and the plural
`sources`* from ONE constant rendered into both the Python and the SQL half (Q-050-3
alignment, parametrized test) — **and the constant carries the VALUE SHAPES too**
(scalar · list of scalars · list of `{…, url: …}` objects · top-level `{url: …}` object),
because enumerating the keys without enumerating the shapes is the same bug one level
down.

**How far that alignment gate actually reaches — stated, because it used to over-claim**
(061 VDD iteration-2 / MED-1). The constant renders the **keys** into both halves, and a
test pins every key into every `IN` list of the SQL, so a key cannot reach one half only.
It does **not** render the **shapes**, and nothing can: a value shape is *control flow*
(an `isinstance` ladder in Python, a `je.type` ladder in SQL), not data. The shape table
in `tests/test_trust_tier.py` is hand-maintained and **neither half reads it** — so a dev
who widened the Python predicate and forgot the SQL kept all its cross-product cases green
(measured, not supposed: **108 passed** under exactly that mutation). The shape half is
therefore gated **differentially** instead:
`test_sql_and_python_agree_on_generated_frontmatter` generates frontmatter from a grammar
that does not know the predicate, and requires `trust_tier(...) == "external"` **⟺** the
row is dropped by `--min-trust internal`. A half-widening fails it in either direction.
It proves the halves **agree**; the *matrix* proves they are **right** — revert a shape on
both halves and they agree again. Two gates, neither redundant.

**The "accepted" row below was NOT acceptable — it was a live fail-open, and it is now
closed** (061 VDD fix-loop / H2). It read: *"List-valued `source:` (a YAML sequence, not a
scalar) — accepted, the derivation reads scalars."* That acceptance was written without a
census. The census: **17 live pages** carry an external URL under a list-valued `sources:`
— 1 partnership note (`sources: [https://…, https://…]`) and 16 course summaries
(`sources: [{id, url: https://…, file}]`, the shape our OWN
`generate-detailed-meeting-summary` emits and our OWN `all_cited_sources` reads). All 17
derived `internal` and passed `--min-trust internal`, the filter whose entire purpose is
the H-6 contract. Both halves agreed with each other throughout; **alignment is not the
security property — FAIL-CLOSED is.** Live external count: **720 → 737** of 3267.

**A second "accepted" row is also now closed, at 0 live pages** (061 VDD iteration-2 /
LOW-3). `source: {url: "https://…"}` — a **top-level object** — derived `internal` on both
halves and passed `--min-trust internal`. It was excused as *"0 live pages, no tool emits
it"*, which is a fact about **tools**: vault frontmatter is **hand-authored and untrusted
(H-6)**, and a mapping under `source:` is a natural thing for a human to type. That is the
*same excuse this very section already retired* for `Source:` — "our own writers use the
canonical shape" is not a property of a vault that also holds content the framework did
not write, and repeating it for a second shape would be the disease, not a decision. It is
closed as a **fourth fixed position** (`_member_is_external` / `_member_sql` are each
written once and rendered at both member positions) — not recursion, no `json_tree`, no
new index. It changes **no live page's tier** (re-censused read-only: still 737 of 3267);
the point is the shape can no longer fail open when someone eventually types it.

What **survives** in (iii), stated rather than assumed:

| Residual | Status |
|---|---|
| **Vault-specific provenance keys** (`youtube:`/`teachable:`) | **OPEN — Q-061-4.** Different *keys*, not case variants and not value shapes; still derive `internal`. **9 pages, not the 18 previously recorded here** — the same 9 pages carry *both* keys, and "18" was two key-occurrence counts summed as if they were disjoint page sets (1 of the 9 is external via another key, so **8** actually fail open). Disjoint from the 17 above. Deferred by **mechanism** (needs a per-vault `external_keys:` config surface), **not** by defect. Test-pinned in its known-wrong state so it stays visible. |
| **Typo-shaped keys** (`uRL:`, `Source_URL:`) | accepted — no tool emits them. NOTE: now that the SQL half is a `json_each` member walk, a true `lower(key)` fold would be **symmetric** across the halves (Q-061-2's rationale for enumerating assumed it could not be) and would close this class. Deliberate follow-up, not a silent widening. |
| **URL under a container nested BELOW an already-walked container** (`sources: [{url: [https://…]}]`, `sources: [{meta: {url: …}}]`, `sources: [[…]]`) | accepted, **0 live pages** — closing these needs a genuinely recursive descent (a `json_tree` walk on the hot search path), not one more fixed position. That is the line: it is drawn at a property of the **walk**, not at a census. All are **test-pinned** so the limit stays visible rather than merely true. |

The tier remains **advisory, never an authorization boundary** — closing a fail-open leak
raises the floor; it does not promote `trust` into access control.
