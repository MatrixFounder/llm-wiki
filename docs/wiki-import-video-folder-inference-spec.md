# wiki-import — video robustness, folder inference & announcement detection (spec)

**Status:** proposed
**Origin:** import of the cyber•Fund *"Building AI-Native Startups [004]"* X‑Broadcast (2026‑07‑09).
Three friction points surfaced on the `wiki-import` side (the fourth, concept compounding, is config —
see §C). This spec is the counterpart to the `transcript-fetcher` skill spec in the Universal‑skills
repo (`docs/transcript-fetcher-skill-improvement-spec.md`); **W1 depends on** the new transcript‑fetcher
flags landing there.

Line references are to `scripts/wiki_skills/wiki_import_article/_fetch.py` unless noted.

---

## Summary

| ID | Problem | Change | Priority |
|----|---------|--------|----------|
| **W1** | Long X Broadcasts/Spaces can't be fetched (transcript‑fetcher serial download times out) | Forward `--concurrent-fragments` / `--media-timeout-sec` through `_fetch_transcript` | **P0** (pairs with the skill spec) |
| **W2** | `--folder` omitted → operator/model **guesses** a folder (mis‑filed the 004 `_raw` under Крипто); the CLAUDE.md hint (`obsidian-active-note`) is **vendor‑bound and timing‑fragile** | Vendor‑independent **series/title folder inference** from the vault index, before any app‑state fallback | **P0** |
| **W3** | An `x.com/<user>/status/<id>` that is only an **announcement of a Broadcast** is fetched as a contentless HTML tweet (chrome + trending) and a junk `_raw` + attachments is written | Detect "announcement → broadcast/space link" and **stop with a route hint** (don't write junk `_raw`) | **P1** |

---

## W1 — Forward the media‑download robustness flags to transcript‑fetcher (P0)

### Problem
`_fetch_transcript()` (L693–721) shells out to the transcript‑fetcher `fetch.py` via the venv
interpreter (`_transcript_python()`, L634–637 — this part is correct). The argv it builds (L705) passes
`--out`, `--lang`, `--with-description`, and optionally `--max-duration-min` /
`--cookies-*`, but has **no** way to pass the fragment‑concurrency / media‑timeout knobs the skill spec
adds (S1/S2). So even a correct `wiki-import prepare --source <broadcast-url>` inherits the serial‑download
timeout and fails on a long broadcast — which is why the 004 import had to bypass `wiki-import` entirely.

### Proposed change
Once transcript‑fetcher exposes `--concurrent-fragments` / `--media-timeout-sec` (skill spec S1/S2):
- Add pass‑through args to `_fetch_transcript()` (and its callers `_fetch_x_status_with_video` L749,
  `_append_embedded_videos` L842) and append them to the argv at L705.
- Surface them on the `wiki-import prepare` CLI (e.g. `--transcript-concurrency`, `--transcript-media-timeout`)
  with sensible defaults, OR rely on the skill's own env/`.env` defaults and simply **not clip** by default.
- Keep `WIKI_TRANSCRIPT_TIMEOUT_S` (the existing subprocess wall‑clock) generous enough to cover the
  parallel download + ASR of a ≥60‑min broadcast.

### Acceptance
- `wiki-import prepare --source https://x.com/i/broadcasts/<id> --kind meeting --folder <F>` produces a
  transcript `_raw` for a ~70‑min broadcast end‑to‑end, with **no** manual `yt-dlp`/`mw` steps.

---

## W2 — Vendor‑independent folder inference when `--folder` is omitted (P0)

### Problem
`prepare` requires a `--folder`. With none supplied, the operator must **guess** before knowing the
content — during the 004 import this filed the raw capture under `05 - Материалы/Криптовалюты/_raw/`
(cyber•Fund is a crypto fund) when it belonged in `03 - Learning/Webinars/` next to **episode 003**.
The CLAUDE.md remedy — resolve the operator's open note via `obsidian-active-note` — is:
- **vendor‑bound** (needs a running, focused Obsidian; a specific companion CLI), and
- **timing‑fragile**: during this import `obsidian-active-note focused` returned *"No active file"* at the
  exact moment it was needed, then resolved correctly minutes later. It is a *hint*, not a contract.

The vault itself already held the answer: a sibling of the **same series** (`Building AI-Native
Startups 003 — Cyberfund воркшоп.md` in `03 - Learning/Webinars/`). That signal is derivable from the
**filesystem + FTS index alone** — no app, no vendor.

### Proposed change
Add a **folder‑inference step** to `wiki-import prepare` when `--folder` is absent (and expose the result
so the orchestrator can confirm/override):

1. **Series/title match (primary, vendor‑independent).** From the detected `title`, derive a stable
   series stem (strip trailing episode numbers / bracketed indices, e.g. `Building AI-Native Startups
   [004]` → `Building AI-Native Startups`). Query the index/FTS for existing notes whose title/filename
   shares that stem; if the top matches agree on a **single containing folder**, propose it (with the
   matched sibling as evidence). This is deterministic and needs only the DB that `wiki-*` already owns.
2. **Active‑note hint (secondary).** Only if (1) is inconclusive, consult `obsidian-active-note`
   (folder of the focused/open note) — treated as an *optional* signal, never the sole one.
3. **Ask (fallback).** If neither resolves, emit a typed `FOLDER_UNRESOLVED` with the top candidates so
   the orchestrator asks the user — instead of silently guessing.

Emit the inference in the `prepare` envelope, e.g.
`{ "folder_inferred": "03 - Learning/Webinars", "basis": "series-sibling", "evidence": ["…003…"], "confidence": "high" }`.
**Do not** write `_raw` into a guessed folder before the folder is confirmed (see W3 / staging).

### Acceptance
- Given the 004 title and an existing 003 note, `prepare` with no `--folder` proposes
  `03 - Learning/Webinars` with the 003 sibling as evidence, **without** a running Obsidian.
- With no sibling and no active note, `prepare` returns `FOLDER_UNRESOLVED` + candidates rather than
  writing anywhere.

### Orchestrator/CLAUDE.md companion rule
Update the vault template CLAUDE.md guidance so the **first** move on a missing folder is a vault
search for a same‑series sibling; `obsidian-active-note` becomes a secondary hint, not the primary path.

---

## W3 — Detect "announcement → Broadcast/Space" tweets; don't write junk `_raw` (P1)

### Problem
`x.com/<user>/status/<id>` stays on the **html** path by default (correct — most tweets are text). But
when the tweet body is essentially *"<title>"* + a link to `x.com/i/broadcasts/<id>` (or `/i/spaces/`),
the html capture yields **no substance** — nav chrome, replies, "Discover more", trending — and `prepare`
still writes a `_raw/<ugly-slug>.md` plus **17 attachment images** (avatars/emoji) into the (guessed)
folder. `--kind auto` then mis‑labels it `thread`. A weaker model would summarise that noise.

### Proposed change
In the html/status path, after extraction, run a cheap **announcement heuristic**: if the reader body is
below a content threshold **and** contains a first‑party `x.com/i/broadcasts/` or `/i/spaces/` link
(the same host‑shape router already used for `--video`), then:
- **Do not** write the contentless `_raw`; instead emit a typed
  `{ "action": "announcement_only", "broadcast_url": "…/i/broadcasts/<id>", "hint": "re-run on the broadcast URL or pass --video" }`
  and stop (exit 0, nothing filed).
- Or, when `--video` is already set, transparently route to `_fetch_x_status_with_video` (existing path)
  so the broadcast is transcribed and concatenated.

Bounds: allowlisted X broadcast/space hosts only (no arbitrary egress — same guarantee as `--video`).

### Acceptance
- `prepare` on the 004 announcement tweet (no `--video`) writes **nothing** and returns
  `announcement_only` with the broadcast URL + route hint.
- With `--video`, it produces the concatenated tweet+transcript note as today.

### Related cleanup cost avoided
This removes the manual cleanup the 004 import required (deleting a junk `_raw` + de‑duping 17
tweet‑only attachments from a **shared** `_raw/_attachments/`).

---

## §C — Concept compounding is configuration, not code

The 004 (and 003) notes were **hand‑authored + `wiki-index-upsert`‑ed**, bypassing `wiki-import`/`wiki-sync`,
so no `_concepts/` pages were filed for the many new entities (JellyPod, Mirage, Structural AI, MF0.AI,
Cloud Routines, Linear, WorkOS, FUSE, PostHog, …). This is **not** a `wiki-import` defect — concept
extraction defaults **ON** when the tool path is used:
- `wiki-sync` delegates each *distil* source to `wiki-import` with `concepts` ON by default
  (`wiki_sync.py:231` `"concepts": sm.extract_concepts`), and this vault's `.wiki/sync.yaml` zone
  `03 - Learning/**` already covers the Webinars folder.
- A zone can make it explicit via a `summarize:` block (see `templates/connector-zone.sync.yaml`):
  `summarize: { profile: meeting, extract_concepts: true }`.

**Resolution (no code change):** file future episodes through the tool (transcript → `wiki-import`/`wiki-sync`,
concepts ON) rather than by hand; optionally add a Webinars‑scoped `summarize:` block. Existing 003/004
can be back‑filled with a one‑time `wiki-extract-concepts` run. (W2/W3 make the tool path pleasant enough
that hand‑authoring stops being the tempting shortcut.)

---

## Test plan
- **W1:** offline argv assertion that the concurrency/media‑timeout flags reach the `fetch.py` argv;
  integration on a real long broadcast (opt‑in, gated on cookies/ASR availability).
- **W2:** unit — series‑stem extraction + index query returns the right folder given a seeded sibling;
  `FOLDER_UNRESOLVED` when none; no filesystem write on the unresolved path.
- **W3:** unit — announcement heuristic classifies the 004‑shaped tweet as `announcement_only` and writes
  nothing; a normal text tweet is unaffected; `--video` still concatenates.

## Risks
- W2 series‑stem heuristic must be conservative (avoid over‑merging distinct series); return "ask" rather
  than mis‑file on low confidence.
- W3 threshold tuning — a genuinely substantive tweet that also links a broadcast should NOT be dropped;
  gate on *both* low‑content AND a broadcast/space link, and always allow `--video`/explicit folder to
  proceed.
