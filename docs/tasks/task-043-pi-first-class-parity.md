# TASK 043 — first-class `pi` (pi.dev) support: AGENTS.md + pi skills + pi permissions

## 0. Meta
- **Task ID:** 043 · **Slug:** `task-043-pi-first-class-parity`
- **ADR:** none new — realises **NF-1 (vendor-agnostic)** for pi; amends the vendor-file
  mechanism (TASK 026's `agent-files.yaml`).
- **Mode:** framework **self-improvement** (vendor wiring + install scripts + templates; no
  schema/`user_version` change — zero-DDL). Reviewers: `code-reviewer` + `security-auditor`
  (the permissions translation is the security-sensitive part).
- **Touches:** `templates/{agent-files.yaml,vault.pi-permissions.json}`,
  `scripts/wiki_index/layout.py` (`SYSTEM_FILES`), `scripts/wiki_skills/wiki_init.py`
  (dedup same-file vendors), `bin/{install-globally,install-project-symlinks}.sh`, repo-root
  `AGENTS.md` + `.pi/extensions/permissions.json`, `.gitignore`; tests
  (`test_wiki_init_flows.py`, `test_wiki_sync.py`); docs (README, manuals EN/RU).

## 1. Goal
Operate the wiki + Obsidian through **pi** at full parity with Claude. Investigation found the
engine is already vendor-neutral (on-PATH `wiki-*`/`obsidian` binaries; skills are `SKILL.md` +
frontmatter — **exactly pi's format**; the `obsidian-cli` resolver's docstring already lists pi).
What was missing was pi's **front door**: an instruction file, pi-format permissions, pi skill
discovery.

### pi conventions (pi.dev) that shaped this
- Reads **`AGENTS.md`** (cross-vendor). · Skills from `.pi/skills/` (project) + `~/.pi/skills/`
  (global), auto-exposed as `/skill:<name>` with `enableSkillCommands`. · Permissions JSON at
  `.pi/extensions/permissions.json` — **no allow-list**, a `mode` + `dangerousPatterns`/
  `catastrophicPatterns`/`protectedPaths`. · Workflows are TS/JS code modules — **out of scope**
  (this framework's markdown workflow *recipes* are skill-referenced prose, not ported).

## 2. What shipped
- **AGENTS.md instruction.** `agent-files.yaml` gains `agents` (→ `AGENTS.md`) and `pi`
  (→ `AGENTS.md` + `.pi/extensions/permissions.json`), both reusing the vendor-neutral
  `CLAUDE.md.tmpl` (gemini precedent). `AGENTS.md` added to `layout.py::SYSTEM_FILES` (reindex /
  wiki-sync skip it). `wiki_init._write_agent_files` dedups a shared filename within one
  `--vendor all` run (so AGENTS.md isn't double-processed for `agents`+`pi`); the settings-write
  already `mkdir -p`s the nested `.pi/extensions/` + containment-checks — no change needed there.
- **pi permissions** `templates/vault.pi-permissions.json`: `mode: fullAuto` (auto-approve safe
  bash, confirm dangerous — the closest analog to the Claude allow-list intent, since pi has no
  allow-list) + `dangerousPatterns`/`catastrophicPatterns`/`protectedPaths` translated from the
  Claude vault deny-list. Written verbatim, non-destructive.
- **Global discovery** `bin/install-globally.sh`: links `wiki-*` **+ `obsidian-cli`** into
  `~/.pi/skills/` (and fixes obsidian-cli's prior omission from the Claude global loop too).
  CLIs are already shared via `~/.local/bin`.
- **Repo dev tree** `bin/install-project-symlinks.sh`: `.pi/skills/<name>` symlinks; committed
  repo-root `AGENTS.md` (vendor-neutral) + `.pi/extensions/permissions.json` (dev posture);
  `.gitignore` mirrors the `.claude`/`.agent` curated-subset pattern for `.pi/`.

## 3. Security note (translation, not 1:1)
pi has **no allow-list**, so parity is a *semantic* translation. `fullAuto` is **default-allow for
bash** (auto-approve safe bash; confirm dangerous) — broader than the Claude curated allow-list
(default-DENY: only listed commands auto-ran, everything else prompted). To keep parity safe, the
`dangerousPatterns` list must therefore gate every destructive surface the Claude allow-list gated
*by omission*. After the security-audit (FAIL→fixed), `dangerousPatterns` covers: the shell
hazards (rm -rf/-fr, sudo, git reset --hard / clean -fd, curl/wget/nc), the obsidian-cli skill's
own **T3** surfaces (`obsidian eval`/`command`/`dev:`/`devtools`/`plugin:`/`plugins:restrict`/
`sync on|off`/`restart`/`reload`/`theme:`/`snippet:`), the **eval-equivalent** template verbs
(`template:insert`, `create template=`), the destructive **T2** writes (`obsidian delete`/`move`/
`rename`/`history:restore`/`sync:restore`), and an SSH-key read guard (`id_rsa`).
`catastrophicPatterns` = `sudo rm -rf /`. `protectedPaths` = `~/.ssh`, `~/.aws`, `.pi`, `.claude`,
`.git` (self-config + history + standing creds).

**Documented residuals (accepted):** (a) substring matching is a footgun-reducer, not an
adversary-proof boundary (`rm  -rf` / `/bin/rm` evade it — same weakness as the Claude glob;
pi independently forces confirmation on `$()`/backtick/pipe-to-shell tricks). (b) pi
`protectedPaths` is a path-prefix list, so the Claude deny-list's secret-read *globs*
(`Read(**/.env|*.pem|*.key)`) cannot be expressed; `id_rsa` is gated as a pattern and `~/.ssh`/
`~/.aws` cover standing creds, but project-local `.env`/`*.pem`/`*.key` reads are NOT blocked
(adding them as substring patterns was rejected — too false-positive-prone, would erode the
no-prompt goal). Additive obsidian writes (`append`/`prepend`/`property:set`) stay auto
(recoverable via history; gating them re-creates the prompt-storm).

## 4. Verification
- **Reviews:** `code-reviewer` **APPROVED** (2 should-fixes applied: stale `agent-files.yaml`
  comment, dedup second-pass test). `security-auditor` **PASS** (first pass FAIL — 1 HIGH +
  3 MED in the permissions translation — all closed; see §3).
- 1672 pytest passed (+4 new: `--vendor agents`; `--vendor pi` writes valid permissions.json with
  the `obsidian command`/`eval`/`delete` gates, non-destructive; `--vendor pi` dedup second-pass
  (AGENTS.md exists + pi perms still write); `--vendor all` envelope incl. AGENTS.md once + pi
  perms; AGENTS.md in SYSTEM_FILES skip), 5 skipped; `mypy --strict scripts/` clean.
- E2E: `wiki-init --scaffold-new … --vendor all` → CLAUDE.md + GEMINI.md + AGENTS.md (==CLAUDE.md,
  written once) + .claude/settings.json + .pi/extensions/permissions.json (valid JSON, mode
  fullAuto). `bin/install-globally.sh` → all 21 skills + obsidian-cli in `~/.pi/skills/`.
  `bin/install-project-symlinks.sh` → `.pi/skills/*` in the repo.

## 5. Out of scope / follow-ups
- pi TS/JS code-workflows (paradigm mismatch with the md recipes).
- A dedicated `AGENTS.md.tmpl` with fully vendor-neutral phrasing (today AGENTS.md inherits the
  cosmetic "Claude" flavour of the shared template — operational content is correct).
- `default_vendors` stays `[claude]`; pi/agents are opt-in (`[claude, agents]` makes every vault
  cross-vendor).
- Verifying pi's exact `settings.json` schema to optionally ship `enableSkillCommands` rather
  than documenting it as a one-time toggle.
