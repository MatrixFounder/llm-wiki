"""Workflow-state + citation domain of the SQLite DAL (TASK 056).

Methods relocated verbatim from the pre-056 monolith: check_query_state,
record_query_state, check_verify_state, record_verify_state,
get_source_state, set_source_state, find_pages_citing_source,
all_cited_sources.

dialect: mostly generic SQL; `json_extract`/`json_each` over
`frontmatter_json` (in the citation readers) map to Postgres `jsonb`
operators (`->`/`->>`/`jsonb_array_elements`).
"""

from __future__ import annotations

import json
import unicodedata
from datetime import datetime, timezone

from scripts.wiki_index.repository import validate_filter_field
from scripts.wiki_index.sqlite_repository._base import SQLiteRepositoryBase


class _StateMixin(SQLiteRepositoryBase):
    """Query/verify/source state (TASK 007/008/019) + citation readers."""

    def check_query_state(self, vault_id: str, query_slug: str) -> str | None:
        """TASK 007 / R-6.6 — recorded `question_hash` for a filed query, or
        None. Defensive NULL guard mirrors `check_idempotency` (L-V3.2)."""
        row = self._connect().execute(
            "SELECT value FROM source_state "
            "WHERE vault_id = ? AND source_kind = 'query' AND scope = ? "
            "AND key = 'question_hash'",
            (vault_id, query_slug),
        ).fetchone()
        if row is None or row["value"] is None:
            return None
        return str(row["value"])

    def record_query_state(
        self, vault_id: str, query_slug: str, question_hash: str,
    ) -> None:
        """TASK 007 / R-6.6 — UPSERT the query-idempotency row in `source_state`
        (`source_kind='query'`, `scope=query_slug`, `key='question_hash'`)."""
        conn = self._connect()
        now = datetime.now(timezone.utc).isoformat()
        with conn:
            conn.execute(
                "INSERT INTO source_state "
                "(vault_id, source_kind, scope, key, value, updated_at) "
                "VALUES (?, 'query', ?, 'question_hash', ?, ?) "
                "ON CONFLICT(vault_id, source_kind, scope, key) DO UPDATE SET "
                "value = excluded.value, updated_at = excluded.updated_at",
                (vault_id, query_slug, question_hash, now),
            )

    def check_verify_state(self, vault_id: str, verification_slug: str) -> str | None:
        """TASK 008 / R-8.6 — recorded `verify_hash` for a filed verdict, or
        None. Defensive NULL guard mirrors `check_query_state` (L-V3.2)."""
        row = self._connect().execute(
            "SELECT value FROM source_state "
            "WHERE vault_id = ? AND source_kind = 'verification' AND scope = ? "
            "AND key = 'verify_hash'",
            (vault_id, verification_slug),
        ).fetchone()
        if row is None or row["value"] is None:
            return None
        return str(row["value"])

    def record_verify_state(
        self, vault_id: str, verification_slug: str, verify_hash: str,
    ) -> None:
        """TASK 008 / R-8.6 — UPSERT the verify-idempotency row in `source_state`
        (`source_kind='verification'`, `scope=verification_slug`,
        `key='verify_hash'`)."""
        conn = self._connect()
        now = datetime.now(timezone.utc).isoformat()
        with conn:
            conn.execute(
                "INSERT INTO source_state "
                "(vault_id, source_kind, scope, key, value, updated_at) "
                "VALUES (?, 'verification', ?, 'verify_hash', ?, ?) "
                "ON CONFLICT(vault_id, source_kind, scope, key) DO UPDATE SET "
                "value = excluded.value, updated_at = excluded.updated_at",
                (vault_id, verification_slug, verify_hash, now),
            )

    def get_source_state(
        self, vault_id: str, source_kind: str, scope: str, key: str
    ) -> str | None:
        """TASK 018 / Q-018-8 — generic `source_state` read. Defensive NULL guard
        mirrors `check_query_state` (a corrupt `value IS NULL` row → None).

        TASK 053 / R1 (DF-6): `scope` (a vault-rel path) is NFC-normalized here — the
        single DAL choke point — so a filesystem-walk-derived NFD key (macOS/iCloud
        decomposes `й`=и+◌̆) and an operator/LLM/JSON-supplied NFC key resolve to the
        SAME row. Covers scan-read, `record`-write, and both `_resummarize` D1 reads in
        one edit; ASCII scopes are a no-op (NFC≡NFD)."""
        scope = unicodedata.normalize("NFC", scope)
        row = self._connect().execute(
            "SELECT value FROM source_state "
            "WHERE vault_id = ? AND source_kind = ? AND scope = ? AND key = ?",
            (vault_id, source_kind, scope, key),
        ).fetchone()
        if row is None or row["value"] is None:
            return None
        return str(row["value"])

    def set_source_state(
        self, vault_id: str, source_kind: str, scope: str, key: str, value: str
    ) -> None:
        """TASK 018 / Q-018-8 — generic `source_state` UPSERT (commit marker).
        `'sync'` needs no DDL: `source_state.source_kind` has no CHECK, so the
        partition is pure data (`user_version` stays 5).

        TASK 053 / R1 (DF-6): `scope` is NFC-normalized on write to match the
        normalized read in `get_source_state` (see there)."""
        scope = unicodedata.normalize("NFC", scope)
        conn = self._connect()
        now = datetime.now(timezone.utc).isoformat()
        with conn:
            conn.execute(
                "INSERT INTO source_state "
                "(vault_id, source_kind, scope, key, value, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(vault_id, source_kind, scope, key) DO UPDATE SET "
                "value = excluded.value, updated_at = excluded.updated_at",
                (vault_id, source_kind, scope, key, value, now),
            )

    def find_pages_citing_source(
        self, vault_id: str, rel_path: str, fields: tuple[str, ...]
    ) -> list[str]:
        """TASK 019 / Q-019-4 — D2a provenance over `pages.frontmatter_json`.

        For each allowlisted `field`, a page cites `rel_path` iff the frontmatter
        value equals it as a **scalar** (`json_extract` + `CAST … AS TEXT`) OR as a
        **list element** (`json_each`, the N:1 `sources: [...]` case). Both the JSON
        path and the value are BOUND parameters (no operator string reaches the SQL
        text). A field failing `validate_filter_field` is skipped (never raises)."""
        conn = self._connect()
        seen: set[str] = set()
        out: list[str] = []
        for field in fields:
            try:
                validate_filter_field(field)
            except ValueError:
                continue  # misconfigured field → skip, never crash the scan
            json_path = f"$.{field}"
            rows = conn.execute(
                "SELECT slug FROM pages WHERE vault_id = ? AND ("
                "  CAST(json_extract(frontmatter_json, ?) AS TEXT) = ?"
                "  OR EXISTS (SELECT 1 FROM json_each(frontmatter_json, ?) "
                "             WHERE value = ?)"
                ")",
                (vault_id, json_path, rel_path, json_path, rel_path),
            ).fetchall()
            for r in rows:
                slug = str(r["slug"])
                if slug not in seen:
                    seen.add(slug)
                    out.append(slug)
        return out

    def all_cited_sources(self, vault_id: str, fields: tuple[str, ...]) -> set[str]:
        """TASK 019 / Q-019-4 (perf) — one `json_each` scan per field → the set of
        all cited source paths. `json_each(frontmatter_json, '$.<field>')` yields the
        scalar for a string field AND each element for a list field (`sources:`), so a
        single query covers both shapes. Path bound as a parameter; field allowlisted
        (non-conforming → skipped). Hoisted once per scan by `_resummarize` to replace
        the per-file N+1 (vdd-multi PERF-HIGH).

        TASK 023 — a `sources:` element may be a STRUCTURED OBJECT (e.g. the
        ``{id, url, file}`` shape emitted by `generate-detailed-meeting-summary`)
        rather than a bare path string. SQLite `json_each` over the list yields
        such an element as the object's JSON text with `type='object'`; we parse
        it and harvest every scalar string member, so a basename/path match can
        still find the citeable value (all members describe the SAME source, so
        harvesting the extra id/url alongside the file path is safe — a false
        match would need an unrelated string to equal the target path/basename)."""
        conn = self._connect()
        out: set[str] = set()
        for field in fields:
            try:
                validate_filter_field(field)
            except ValueError:
                continue
            json_path = f"$.{field}"
            rows = conn.execute(
                "SELECT je.value AS v, je.type AS t FROM pages, "
                "json_each(pages.frontmatter_json, ?) je "
                "WHERE pages.vault_id = ? AND je.value IS NOT NULL",
                (json_path, vault_id),
            ).fetchall()
            for r in rows:
                if r["t"] == "object":
                    try:
                        obj = json.loads(r["v"])
                    except (TypeError, ValueError):
                        continue
                    if isinstance(obj, dict):
                        for sv in obj.values():
                            if isinstance(sv, str) and sv:
                                out.add(sv)
                    continue
                out.add(str(r["v"]))
        return out

