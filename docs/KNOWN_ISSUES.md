<!-- GENERATED-AT: 2026-06-01T16:57:37.671351 by wiki-index-render --auto-indexes -->
# Known Issues — obsidian-llm-wiki

## dogfood

- **DF-1** [[df-1-wiki-search-crashes-on-a-hyphenated-bare-query|wiki-search crashes on a hyphenated bare query]] — status `fixed`, opened 2026-05-29
- **DF-2** [[df-2-entity-resolution-clis-leave-transient-page-level-class-b-drift|entity-resolution CLIs leave transient page-level Class B drift]] — status `by-design`, opened 2026-05-29
- **DF-3** [[df-3-wiki-init-scaffold-writes-invalid-yaml-wiki-schema-md|wiki-init scaffold writes invalid-YAML WIKI_SCHEMA.md]] — status `fixed`, opened 2026-05-29
- **DF-4** [[df-4-wiki-alias-add-did-not-refuse-a-cross-name-hijack|wiki-alias --add did not refuse a cross-NAME hijack]] — status `fixed`, opened 2026-05-29
- **DF-5** [[df-5-wiki-alias-add-created-a-redundant-self-alias|wiki-alias --add created a redundant self-alias]] — status `fixed`, opened 2026-05-29
- **DF-Q1** [[df-q1-natural-language-questions-returned-no-context|natural-language questions returned NO_CONTEXT]] — status `fixed`, opened 2026-05-29
- **DF-V1** [[df-v1-verdict-page-pages-pk-collides-with-the-audited-query-page|verdict-page \`pages\` PK collides with the audited query page]] — status `fixed`, opened 2026-05-29

## logic

- **L-1** [[l-1-entities-file-path-unique-invariant-not-explicit|entities.file_path UNIQUE invariant not explicit]] — status `fixed`, opened 2026-05-26
- **L-2** [[l-2-log-events-event-date-should-be-generated-always-column|log_events.event_date should be GENERATED ALWAYS column]] — status `fixed`, opened 2026-05-26
- **L-3** [[l-3-interactions-id-is-three-identifiers-in-one|interactions.id is three identifiers in one]] — status `open`, opened 2026-05-26
- **L-4** [[l-4-entity-aliases-pk-includes-entity-slug-wrong|entity_aliases PK includes entity_slug (wrong)]] — status `fixed`, opened 2026-05-26
- **L-5** [[l-5-pages-type-log-is-dead-enum-value|pages.type='log' is dead enum value]] — status `fixed`, opened 2026-05-26
- **L-6** [[l-6-known-concepts-view-has-cold-call-cost|known_concepts view has cold-call cost]] — status `fixed`, opened 2026-05-26
- **L-7** [[l-7-adr-002-ssd8-anti-pattern-table-correctness-re-verify|ADR-002 §D8 anti-pattern table correctness re-verify]] — status `fixed`, opened 2026-05-26
- **L-V3.1** [[l-v3-1-datetime-import-inside-update-idempotency-state|datetime import inside update_idempotency_state]] — status `fixed`, opened 2026-05-28
- **L-V3.2** [[l-v3-2-check-idempotency-missing-defensive-null-check|check_idempotency missing defensive NULL check]] — status `fixed`, opened 2026-05-28
- **L-V3.3** [[l-v3-3-anthropic-sdk-exception-chain-may-leak-metadata|Anthropic SDK exception-chain may leak metadata]] — status `fixed`, opened 2026-05-28
- **L-008-2** [[l-008-2-verify-hash-keys-on-the-cited-source-set-not-source-content|verify_hash keys on the cited-source SET, not source content]] — status `documented`, opened 2026-05-29
- **L-8** [[l-8-reindex-stores-entities-name-from-frontmatter-title-not-name|reindex stores entities.name from frontmatter \`title\`, not \`name\`]] — status `fixed`, opened 2026-05-29
- **L-009-4** [[l-009-4-enriched-security-lens-over-reaches-onto-numeric-factual-errors|enriched \`security\` lens over-reaches onto numeric-factual errors]] — status `fixed`, opened 2026-05-30
- **L-009-5** [[l-009-5-residual-factual-completeness-cross-bleed|residual factual↔completeness cross-bleed]] — status `fixed`, opened 2026-05-30
- **L-008-1** [[l-008-1-verification-slug-not-length-capped|\`verification_slug\` not length-capped]] — severity `LOW`, status `open`, opened 2026-05-29
- **L-009-1** [[l-009-1-completeness-is-the-leakiest-lens-3-residual-purity-violations|\`completeness\` is the leakiest lens (3 residual purity violations)]] — severity `LOW`, status `open`, opened 2026-05-29
- **L-009-2** [[l-009-2-severity-metric-is-exact-match-to-floor-doesn-t-reward-consistency|severity metric is exact-match-to-floor, doesn't reward consistency]] — severity `LOW`, status `open`, opened 2026-05-29
- **L-009-3** [[l-009-3-few-shot-defang-contract-is-a-token-allow-list-not-a-structural-check|few-shot defang contract is a token allow-list, not a structural check]] — severity `LOW`, status `open`, opened 2026-05-29
- **L-9** [[l-9-entity-resolution-minor-logic-ux-nits-deferred|entity-resolution minor logic/UX nits (deferred)]] — severity `LOW`, status `open`, opened 2026-05-29

## performance

- **P-1** [[p-1-reindex-full-per-page-transactions|reindex_full per-page transactions]] — status `open`, opened 2026-05-26
- **P-2** [[p-2-reindex-delta-no-op-walk-cost|reindex_delta no-op walk cost]] — status `open`, opened 2026-05-26
- **P-3** [[p-3-check-drift-re-hashes-every-file|check_drift re-hashes every file]] — status `open`, opened 2026-05-26
- **P-4** [[p-4-benchmark-suite-default-n-100-only|benchmark suite default n=100 only]] — status `open`, opened 2026-05-26
- **P-5** [[p-5-idx-pages-vault-tags-is-dead-weight-functional-index|idx_pages_vault_tags is dead-weight functional index]] — status `fixed`, opened 2026-05-26
- **P-10** [[p-10-wiki-lint-frontmatter-scan-is-a-2nd-o-pages-yaml-sweep|wiki-lint frontmatter scan is a 2nd O(pages) YAML sweep]] — status `fixed`, opened 2026-05-29
- **P-6** [[p-6-known-concepts-payload-o-n-per-prepare-invocation|known_concepts payload O(N) per prepare invocation]] — severity `SEV-2`, status `open`, opened 2026-05-28
- **P-7** [[p-7-no-batch-surface-for-n-source-page-workflows|no batch surface for N-source-page workflows]] — severity `SEV-2`, status `open`, opened 2026-05-28
- **P-8** [[p-8-wal-pragma-setup-cost-compounded-across-the-two-process-workflow|WAL PRAGMA setup cost compounded across the two-process workflow]] — severity `SEV-2`, status `open`, opened 2026-05-28
- **P-9** [[p-9-missing-concept-files-o-n-stat-sweep-in-prepare|missing_concept_files O(N) stat sweep in prepare]] — severity `SEV-3`, status `open`, opened 2026-05-28
- **P-11** [[p-11-find-alias-collisions-cross-name-join-on-unindexed-entities-name|find_alias_collisions cross-name join on unindexed entities.name]] — severity `SEV-3`, status `open`, opened 2026-05-29
- **R-X1-CFG-COST** [[r-x1-layout-config-resolve-cost|Per-command layout-config resolve cost (no cache; per-file regex recompile)]] — severity `SEV-3`, status `open`, opened 2026-06-01
- **R-X1-OBS-WALK** [[r-x1-obsidian-multiglob-rewalk|obsidian-personal multi-glob subtree re-walk]] — severity `SEV-3`, status `open`, opened 2026-06-01

## quality

- **Q17** [[q17-source-not-found-vs-invalid-source-path-info-disclosure-oracle|SOURCE_NOT_FOUND vs INVALID_SOURCE_PATH info-disclosure oracle]] — status `documented`, opened 2026-05-28
- **Q-007-3** [[q-007-3-apply-question-changed-if-a-retrieval-scope-flag-is-omitted|\`apply\` QUESTION_CHANGED if a retrieval-scope flag is omitted]] — status `documented`, opened 2026-05-29
- **Q-007-4** [[q-007-4-cited-slug-rendered-into-a-sources-slug-wikilink-unsanitized|cited slug rendered into a \`## Sources \[\[slug\]\]\` wikilink unsanitized]] — status `documented`, opened 2026-05-29
- **Q-007-1** [[q-007-1-wiki-query-apply-re-runs-the-full-retrieval-to-recompute-the-hash|\`wiki-query apply\` re-runs the full retrieval to recompute the hash]] — severity `SEV-3`, status `open`, opened 2026-05-29
- **Q-007-2** [[q-007-2-self-index-re-reads-the-just-written-query-page|self-index re-reads the just-written query page]] — severity `SEV-3`, status `open`, opened 2026-05-29

## security

- **D-1** [[d-1-assert-no-symlink-escape-limited-on-unix|assert_no_symlink_escape limited on Unix]] — status `documented`, opened 2026-05-26
- **D-2** [[d-2-r-26-not-enforced-on-cli-output-paths|R-26 not enforced on CLI output paths]] — status `open`, opened 2026-05-26
- **H-5** [[h-5-concept-extraction-skill-md-integrity-is-trust-the-committer|concept-extraction SKILL.md integrity is "trust the committer"]] — status `open`, opened 2026-05-28
- **H-6** [[h-6-indirect-prompt-injection-via-source-body|indirect prompt injection via source_body]] — status `open`, opened 2026-05-28
- **D-010-1** [[d-010-1-cross-source-conflict-lens-rule-deferred-prompt-change|cross-source conflict lens rule (deferred prompt change)]] — status `fixed`, opened 2026-05-31
- **D-010-2** [[d-010-2-completeness-omission-bleed-on-inversion-defects-v3-quantified|completeness-omission bleed on inversion defects (v3-quantified)]] — status `mitigated`, opened 2026-05-31
- **H-PERF-3** [[h-perf-3-index-from-manifest-argparse-in-loop|index_from_manifest argparse-in-loop]] — severity `SEV-2`, status `open`, opened 2026-05-28
- **R-X1-REDOS-RT** [[r-x1-redos-runtime-deadline-residual|ReDoS load-gate residual — no per-file runtime regex deadline]] — severity `SEV-2`, status `open`, opened 2026-06-01

## uncategorized

- **N-008-1** [[n-008-1-exit-6-for-a-fail-verdict-diverges-from-the-family-6-error-convention|\`exit 6\` for a FAIL verdict diverges from the family \`6=error\` convention]] — status `documented`, opened 2026-05-29

## ux

- **R-X3-META-FILTER** [[r-x3-fts-frontmatter-metadata-filter|wiki-search can't filter by frontmatter metadata (status / severity / category)]] — severity `SEV-3`, status `open`, opened 2026-06-01
