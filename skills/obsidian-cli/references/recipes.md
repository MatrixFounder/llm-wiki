# Obsidian CLI — recipes (composed playbooks)

End-to-end playbooks composing the native CLI with the `wiki-*` toolchain. **Conventions
(binding):** every mutating command carries an explicit `path=` AND `vault=` (the CLI
defaults to the *active file* otherwise — SKILL.md targeting discipline); each recipe ends
with a **Coherence** step (wiki-registered vault) or an explicit *No mutation — no
coherence step*; request `format=json` only where the command reference says it is
available.

**Placeholders** (the two systems name vaults differently — SKILL.md targeting):
- `<v>` — the **Obsidian vault NAME** (for `obsidian vault=<v> …`).
- `<vid>` — the **wiki `vault_id`** (for `wiki-* --vault <vid>` — note `--vault`, singular;
  only `wiki-search`/`wiki-query` take the plural `--vaults`).
- `$VR` — the vault's **absolute root path**, e.g. `VR=$(obsidian vault=<v> vault info=path)`
  (`wiki-index-upsert --source` needs an ABSOLUTE path inside the vault root).
Confirm `<v>`↔`<vid>` map to the same directory once: `obsidian vaults verbose` path ==
the wiki's registered `vault_root`.

---

## 1. Link-safe rename / move

**Goal:** rename or move a note without breaking inbound `[[wikilinks]]`.
**Preconditions:** CLI available (`obsidian help`); vault identity confirmed; in Obsidian,
*Settings → Files & Links → Automatically update internal links* is **ON** (verify once per
vault — without it the app does not rewrite backlinks).

```bash
# baseline (for the coherence proof)
wiki-lint --vault <vid> | grep -i orphan       # note the count

# rename (app rewrites every inbound wikilink):
obsidian vault=<v> rename path="Areas/Health.md" name="Wellbeing"
# OR move into another folder:
obsidian vault=<v> move path="Notes/raw-idea.md" to="Archive/raw-idea.md"
```

**Coherence:** since framework TASK 030 `wiki-reindex --delta` is **rename-aware** — it
ingests the moved file's new path despite the preserved mtime (the original DF-029-1 trap)
and reports it under `new_path_ingested`:
```bash
wiki-reindex --delta --vault <vid>             # rename-aware: absorbs the moved file
wiki-lint --vault <vid> | grep -i orphan       # MUST equal the baseline — zero new orphans
# Fallback (pre-TASK-030 framework, or the swap-class residual — two notes that
# EXCHANGED paths are invisible to the delta predicate; lint hash-drift flags them):
# wiki-reindex --full --vault <vid>
```
**Failure handling:** target name already exists → the CLI errors; report it verbatim and
propose a different name — never pass a force/overwrite flag to win a collision. If the
orphan count rose, either the "update internal links" setting was off (→ restore from
`history` and re-run with it on), or you used a plain `--delta` and hit the mtime gap (→
re-run `--full`).

---

## 2. Capture to the daily note

**Goal:** append a quick capture to today's daily note.
**Preconditions:** `obsidian help daily:append` confirms the Daily Notes plugin is enabled
(it is plugin-gated).

```bash
obsidian vault=<v> daily:append content="- [ ] call Anna tomorrow"
VR=$(obsidian vault=<v> vault info=path)        # absolute vault root
DAILY=$(obsidian vault=<v> daily:path)          # the daily note path
```
**Coherence (registered vault):** upsert the daily note (resolve to an absolute path under
the vault root if `daily:path` returned a relative one):
```bash
case "$DAILY" in /*) SRC="$DAILY";; *) SRC="$VR/$DAILY";; esac
wiki-index-upsert --vault <vid> --source "$SRC"
```
**Failure handling:** `obsidian help daily:append` shows nothing → plugin disabled; either
ask the operator to enable Daily Notes, or compute the daily path from the plugin's
date format and `append path=<that path> content=…` instead. Unregistered vault → skip the
upsert (say so).

---

## 3. Task sweep

**Goal:** find open tasks in a scope and mark some done.
**Preconditions:** CLI available.

```bash
VR=$(obsidian vault=<v> vault info=path)
obsidian vault=<v> tasks todo path="Projects/" format=json     # bounded scope + JSON
# for each task to close (ref is path:line from the JSON):
obsidian vault=<v> task ref="Projects/Alpha.md:42" done
```
**Coherence:** upsert each file whose tasks changed:
`wiki-index-upsert --vault <vid> --source "$VR/Projects/Alpha.md"`.
**Failure handling:** a `ref` whose line moved (file edited since the listing) → re-run
`tasks` to refresh refs before toggling; never toggle by stale line number.

---

## 4. Base → JSON → analysis

**Goal:** pull structured rows out of a Base and reason over them.
**Preconditions:** `obsidian help base:query` confirms Bases is enabled.

```bash
obsidian vault=<v> bases                                  # find the .base file
# base:views lists views of the CURRENT base (no path= param) — open the base to make it current:
obsidian vault=<v> open path="Projects.base"
obsidian vault=<v> base:views                             # view names of the now-current base
# base:query DOES take path= — query the target base directly:
obsidian vault=<v> base:query path="Projects.base" view="Overdue" format=json
```
Analyse the returned JSON in-context and answer; cite the query output, not training data.
**No mutation — no coherence step.**
**Failure handling:** unknown view → `open` the base then `base:views` (it reads the current
base only — it has no `path=`). Bases disabled → fall back to `wiki-search`/file reads if the
data is plain frontmatter; otherwise report the gate.

---

## 5. Property migration

**Goal:** set/normalise a typed frontmatter property across a set of notes.
**Preconditions:** CLI available; know the target type (`text|list|number|checkbox|date|datetime`).

```bash
VR=$(obsidian vault=<v> vault info=path)
obsidian vault=<v> properties counts                      # survey current property usage
# per file (explicit path each time):
obsidian vault=<v> property:set path="Areas/Health.md" name="status" value="active" type="text"
```
**Coherence:** `wiki-index-upsert --vault <vid> --source "$VR/Areas/Health.md"` per changed file.
**Failure handling:** wrong `type=` makes Obsidian store the value oddly → `property:read` to
verify, `property:remove` + re-set if needed. Batch carefully — one `property:set` per file,
each with its own `path=`.

---

## 6. History recovery

**Goal:** restore a clobbered note from local file recovery.
**Preconditions:** File Recovery has snapshots for the file (snapshots accrue on edit over
time; a brand-new note may have none).

```bash
VR=$(obsidian vault=<v> vault info=path)
obsidian vault=<v> history path="Notes/Important.md"            # list versions
obsidian vault=<v> history:read path="Notes/Important.md" version=2   # inspect the candidate
# SHOW the operator the version (or diff vs current) and get explicit confirmation, THEN:
obsidian vault=<v> history:restore path="Notes/Important.md" version=2
```
**Coherence:** `wiki-index-upsert --vault <vid> --source "$VR/Notes/Important.md"`.
**Failure handling:** restore is destructive of the current content → in an autonomous run,
STOP after `history:read` and report options; never restore without showing the target
version first. No versions → report honestly; offer `sync:history`/`sync:restore` if Sync is
enabled.

---

## 7. Vault audit

**Goal:** cross-check the live link graph against the wiki index.
**Preconditions:** CLI available; vault registered in the wiki.

```bash
obsidian vault=<v> orphans total
obsidian vault=<v> deadends total
obsidian vault=<v> unresolved counts format=json
wiki-lint --vault <vid>                                   # the indexed view
```
Reconcile: the app counts links **live** (current file state); `wiki-lint` counts the
**indexed** view. A discrepancy usually means the index is stale →
`wiki-reindex --delta --vault <vid>` and re-compare.
**No mutation — no coherence step** (unless you reindex to reconcile, which is itself the
coherence action).
**Failure handling:** large `unresolved` list → use `format=json` + bounded review; a
persistent gap after `--delta` points to a layout/config issue (see `wiki-lint` docs), not a
CLI problem.

---

## 8. Workspace / session setup

**Goal:** arrange panes/tabs for a working session.
**Preconditions:** CLI available.

```bash
obsidian vault=<v> workspace                              # inspect current layout (T1)
obsidian vault=<v> open path="Dashboards/Today.md" newtab
obsidian vault=<v> tab:open file="Projects/Alpha.md"
```
These are T1/T1-UX (open/GUI state, no on-disk note change).
**No mutation — no coherence step.**
**Failure handling:** `workspace:save`/`workspace:load` are plugin-gated/doc-only on some
builds → feature-detect with `obsidian help workspace:save` before relying on them.

---

## 9. Operate on the active / open note (no path given)

**Goal:** the user, in Obsidian's shell, says *"edit the note"* / *"the note about github
setup"* with **no path** → resolve the active/open note and act on the **explicit** resolved
path (TASK 041 / ADR-008; SKILL.md "Active-note resolution"). **Preconditions:** CLI available;
**not headless** (decide from the environment FIRST — the resolver runs `obsidian` subcommands
that launch the GUI). The resolver is the stdlib helper `obsidian-active-note`.

```bash
# A — bare reference ("the/current note") → focused tab (MEDIUM: confirm 1st time per session)
obsidian-active-note focused --expect-vault <v> --format json
#   exit 0 → {"path":"Areas/Health.md","abs":"/…/Areas/Health.md","vault":"<v>"} ; exit 3 → ASK

# B — descriptor ("note about github setup") → unique OPEN tab + vault-unique basename (HIGH: no ask)
obsidian-active-note match --descriptor "github setup" --expect-vault <v> --format json
#   exit 0 → resolved note (proceed, no ask) ; exit 7 (many open / non-unique basename) / 3 (none) → ASK

# then act on the RESOLVED explicit path (never the implicit active-file default):
VR=$(obsidian vault=<v> vault info=path)
obsidian vault=<v> append path="Areas/Health.md" content="## Follow-ups"
```

**Confidence → confirmation:** HIGH (descriptor→unique open tab) = no ask · MEDIUM (bare
ref→focused tab) = confirm first-per-session, then trust · LOW (none/many/split-pane) = ASK.
**Destructive verbs (`delete`/`move`/`rename`) ALWAYS re-confirm** regardless (E-14).
**Coherence:** registered vault → same-turn `wiki-index-upsert --vault <vid> --source "$VR/Areas/Health.md"`.
**Failure handling:** exit 6 `vault-mismatch` (the focused tab is in another vault) → surface it,
don't act; exit 5 `cli-absent` / headless → degrade per SKILL.md, ask for an explicit path. Never
fall back to the active tab when the user named a *different* note (that's the LOW→ASK case).
