# Known Issues

## Entry format

## [YYYY-MM-DD] <short-title> [STATUS: open|fixed|wontfix]

## Low-severity items from some-review

## [2026-05-26] L-1 entities.file_path UNIQUE invariant not explicit [STATUS: fixed 2026-05-29]

- **Symptom**: invariant implicit.
- **Root cause**: doc gap.
- **Fix plan**: add comment.

## [2026-05-26] P-1 reindex_full per-page transactions [STATUS: open]

- **Symptom**: N transactions.
- **Fix plan**: bulk-tx.

## Performance section header

## [2026-05-28] P-6 known_concepts payload O(N) [STATUS: open, SEV-2]

- **Symptom**: O(N) per call.

## [2026-05-29] DF-2 transient drift [STATUS: by-design / documented]

- **Symptom**: expected.

## [2026-05-28] ZZ-9 mysterious widget [STATUS: open]

- **Symptom**: unknown prefix → should be flagged.
