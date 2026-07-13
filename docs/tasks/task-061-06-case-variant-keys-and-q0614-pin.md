# Task 061-06 — [LOGIC] Case-variant provenance keys + the Q-061-4 residual, test-pinned

RTM: **R-061-3** (behavior half). Depends on: `061-04`.

## Goal

Close the observed leak: LIVE pages carry `Source:` (a case variant) and derive as
`internal` — the trust layer **fails OPEN**. With `061-04` in place this is a **one-tuple edit**
plus its honest documentation.

> **CENSUS CORRECTED — this spec said "18 LIVE pages", and 18 is not the fail-open count**
> (061 VDD iteration-2 / LOW-2). Re-counted read-only against the live vault: **19** pages
> carry the KEY `Source:`; **18** carry an `http(s)` scalar under it; **13** of those
> actually derived `internal` (the other 5 were already `external` via a canonical
> `source`/`url`/`URL` key). **13 is the number** — and the shipped arithmetic always said
> so (pre-061 external 707 + 13 = 720, + 17 from the H2 shapes = 737). Three surfaces
> carried "18"/"19" with no executable gate on any of them, inside the very task whose
> thesis is *a check that examined nothing reports green*. The reconciled number now lives
> in ONE place — `policy.EXTERNAL_PROVENANCE_KEYS` — **with its re-runnable read-only
> query beside it**.

## Changes

### `scripts/wiki_index/policy.py`

```python
EXTERNAL_PROVENANCE_KEYS: tuple[str, ...] = (
    "source", "Source", "SOURCE", "url", "Url", "URL")
```

Both halves re-render automatically (`_is_external`, `_EXT`: 8 → **14** `LIKE` disjuncts) and
the parametrized alignment test (TC-04-1) automatically grows to 12 key×scheme cases. **That is
the whole point of `061-04`.**

Docstring must state, in the same breath (Q-061-2, verbatim intent):

- Enumeration (not case-folding) is forced by the **Q-050-3 alignment** constraint, not by
  performance: SQL `json_extract` paths are case-**sensitive**, so a true fold needs
  `json_each` + `lower(key)` **in SQL only** — the asymmetric fix Q-050-3 forbids.
- **Honest limit:** this closes 100% of the *observed* leak, **not a class** — a typo-shaped key
  (`uRL:`, `Source_URL:`) still fails open; no tool emits those.
- `SOURCE`/`Url` have **0** LIVE pages: cheap defense-in-depth. **Do NOT cite P-5** here — P-5 is
  about speculative *indexes*.
- **Residual (Q-061-4):** vault-specific keys (`youtube:` 9, `teachable:` 9 — 18 http-valued
  pages) still derive `internal`. Deferred **by mechanism** (a per-vault `external_keys:` config
  surface does not belong in a fix task), **not by defect**.

## Test cases — `tests/test_trust_tier.py`

1. **TC-06-1 (the fix)** — `{"Source": "https://x.test/a"}` ⇒ `trust_tier == "external"` **and**
   excluded by `--min-trust internal` on **all three query shapes** (the existing corpus test
   already covers FTS / metadata-scan / FTS-narrowed — extend the corpus, don't fork it).
2. **TC-06-2 (alignment auto-grows)** — TC-04-1 now runs 12 key×scheme params, unedited.
3. **TC-06-3 (the residual, PINNED — the task's own ethic applied to itself)** — new
   `test_vault_specific_provenance_key_still_internal_q0614`:

```python
def test_vault_specific_provenance_key_still_internal_q0614(repo):
    """Q-061-4 (KNOWN RESIDUAL, tracked): a page whose provenance is an http(s) URL under a
    VAULT-SPECIFIC key (`youtube:`/`teachable:`) still derives `internal` — the trust contract
    is about external ORIGIN, not key spelling, so this IS a defect; it is deferred by
    MECHANISM (it needs a per-vault `external_keys:` config surface).

    When Q-061-4 lands, FLIP this assertion to "external" — do not delete it."""
    assert trust_tier({"youtube": "https://youtu.be/x"}, "_sources/a.md", False) == "internal"
    # ...and it SURVIVES the --min-trust internal floor (the SQL half agrees — still fail-open)
```

   The test asserts the **SQL half too**, so the two halves stay pinned together even in the
   known-wrong state (an invisible residual becomes a visible, tracked one).

4. **TC-06-4 (blast radius)** — default search output (no `--min-trust`) is **unchanged** for the
   `Source:` corpus page: it still ranks and returns. Only explicit
   `--min-trust internal|verified` callers see it drop out. Assert both directions.

## Docs (this bead's share; the rest is `061-09`)

- `skills/wiki-query/SKILL.md:87` and `docs/architectures/functional/policy-and-trust.md:38`:
  state the key list **with its case variants** (or point at `policy.EXTERNAL_PROVENANCE_KEYS`)
  **and** the Q-061-4 residual in the same breath — *"after TASK 061, pages carrying
  vault-specific provenance keys (`youtube:`/`teachable:`) still derive `internal` — Q-061-4"*.
- Blast radius, stated where operators read it: **default search output is UNCHANGED**; only
  explicit `--min-trust internal|verified` callers see those pages drop out.

## Verification

```bash
source .venv/bin/activate
pytest tests/test_trust_tier.py tests/test_trust_key_single_source.py -q
pytest tests/ -q                      # full suite: the 3-shape floor tests must not regress
mypy --strict scripts/
```

## Acceptance criteria

- [ ] `Source:`-keyed pages derive `external` on **both** halves; `_EXT` has 14 disjuncts.
- [ ] The Q-061-4 residual is **test-pinned** with a docstring that says how to flip it.
- [ ] Docs state the residual **and** the blast radius; no doc claims a "36-page fix".
