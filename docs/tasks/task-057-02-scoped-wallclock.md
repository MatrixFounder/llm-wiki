# 057-02 — [W1-3] scoped transcript wall-clock (3600 primary / 300 embeds)

**Goal:** a ≥60-min broadcast is no longer clipped by the 300 s subprocess wall-clock, while
best-effort embedded fetches keep today's 300 s bound (Q-057-2).

**Context (read):** `_fetch.py:165` `_TRANSCRIPT_TIMEOUT_DEFAULT`, :640 `_transcript_timeout`,
:722 the `subprocess.run(..., timeout=_transcript_timeout())` call; ARCHITECTURE §2.3.5 W1.

**Steps:**
1. Constants: `_TRANSCRIPT_TIMEOUT_PRIMARY_S = 3600`, `_TRANSCRIPT_TIMEOUT_EMBED_S = 300`
   (retire the old single default; keep the `Q-044-4` env-override comment lineage).
2. `_transcript_timeout(primary: bool = True) -> int`: `WIKI_TRANSCRIPT_TIMEOUT_S` set +
   parseable → that value for BOTH roles; else per-role default. Invalid env → per-role
   default (existing ValueError posture).
3. `_fetch_transcript` gains `primary: bool = True`; `_append_embedded_videos` calls with
   `primary=False`; all other callers stay primary. Docstring: hang-guard vs pacing rationale.

**Tests:** no env → 3600 primary / 300 embed (assert the `timeout=` passed to the
monkeypatched `subprocess.run` on a primary vs embed path); env `120` → 120 both;
env garbage → defaults.

**Verification:** `pytest tests/test_import_video.py -q`; `mypy --strict scripts/`.
