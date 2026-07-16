# TASK 070-02 — [R-070-4 + R-070-9] The gate, written before the thing it gates is fixed

**Goal:** build script + receipt + 3-layer drift gate + tsc gate. All RED on arrival — by construction, not by pretence.

**Context:** `scripts/pin_skill_integrity.py` + `config/skill-integrity.sha256` (the idiom to mirror). Design: `design-drift-gate.md` (scratchpad).

**Steps**
1. `scripts/build_agent_bridge.py`: `ESBUILD_ARGV = ("main.ts","--bundle","--external:obsidian","--external:@codemirror/view","--external:@codemirror/state","--format=cjs","--target=es2018","--platform=browser","--log-level=warning")`. `build()` runs with **`cwd=PLUGIN_DIR`, relative entry, `check=True`**.
   - **cwd is load-bearing**: esbuild stamps the entry path — rel `05d906d4…` vs abs `3b3a3645…`.
2. **Per-tool predicates** — `_esbuild_present()`, `_tsc_present()`. **Never one shared `toolchain_present()`** (hazard: esbuild absent + tsc present ⇒ the tsc gate skips though it could run).
3. `--write`: run `tsc --noEmit` **first**; **refuse to re-pin on error**; **HARD-FAIL if tsc is absent — never skip**.
4. `config/agent-bridge-build.json` — define its SHAPE (sha256(main.ts), sha256(main.js), esbuild
   version+argv, tsc version + "0 errors"), but **do NOT create the file**. It cannot honestly exist
   here: `--write` refuses on a type error and 070-01 guarantees 3. **L0 must treat a MISSING receipt
   as RED (drift) — never as an error, never as a skip**; un-pinned IS the drift state L0 exists for.
   The first honest receipt is minted by **070-05** (its `npm run build` = `--write`, which re-pins by
   definition, once 070-03 has cleared the errors); 070-07 re-affirms it under the live gate.
   🛑 **Three distinct bypasses, all banned:** `--force` (skips the tsc refusal), `--build-only`/`--no-pin`
   (builds without re-pinning ⇒ L0 stays red through 070-06), and hand-authoring a `"0 errors"` nobody
   proved — a lie in the artifact whose entire job is to not be one.
5. `tests/test_agent_bridge_build_drift.py`: **L0** hash-pin both files, zero toolchain · **L1** byte-compare · **L2** `WIKI_STRICT_PLUGIN_BUILD=1` ⇒ skip becomes failure (**latent** — no CI sets it; see `docs/issues/arch-10-*`). Skip = toolchain absence ONLY. **Never `except Exception: skip`.**
6. Include **`test_bundle_externalizes_what_obsidian_provides_at_runtime`** — the sole guard for a build-green catastrophe.

**Verification** — `pytest tests/test_agent_bridge_build_drift.py` → **RED** (L1: `e14f5e08…` ≠ `05d906d4…`; tsc: 3 errors). `mypy --strict scripts/` clean.
