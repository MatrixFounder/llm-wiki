"""Vault-registry domain of the SQLite DAL (TASK 056).

Methods relocated verbatim from the pre-056 monolith: register_vault,
get_vault, list_vaults, rename_vault, get_vault_by_root_path, _row_to_vault.

dialect: generic SQL (plain CRUD over `vaults`; portable to Postgres as-is —
only the IntegrityError type changes with the driver).
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from scripts.wiki_index.models import Vault
from scripts.wiki_index.sqlite_repository._base import (
    SQLiteRepositoryBase,
    VaultRegistrationError,
)


class _VaultsMixin(SQLiteRepositoryBase):
    """Vault registry CRUD (task-001-15)."""

    def register_vault(self, vault: Vault) -> None:
        conn = self._connect()
        config_json = json.dumps(vault.config_json) if vault.config_json is not None else None
        try:
            conn.execute(
                "INSERT INTO vaults (vault_id, name, root_path, schema_version, "
                "registered_at, config_json, notes) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    vault.vault_id,
                    vault.name,
                    str(vault.root_path),
                    vault.schema_version,
                    vault.registered_at.isoformat(),
                    config_json,
                    vault.notes,
                ),
            )
        except sqlite3.IntegrityError as e:
            raise VaultRegistrationError(
                f"failed to register vault_id={vault.vault_id!r} "
                f"root_path={vault.root_path}: {e}"
            ) from e

    def get_vault(self, vault_id: str) -> Vault | None:
        conn = self._connect()
        row = conn.execute(
            "SELECT vault_id, name, root_path, schema_version, registered_at, "
            "config_json, notes FROM vaults WHERE vault_id = ?",
            (vault_id,),
        ).fetchone()
        if row is None:
            return None
        return self._row_to_vault(row)

    def list_vaults(self) -> list[Vault]:
        conn = self._connect()
        rows = conn.execute(
            "SELECT vault_id, name, root_path, schema_version, registered_at, "
            "config_json, notes FROM vaults WHERE vault_id != '_global_' "
            "ORDER BY vault_id"
        ).fetchall()
        return [self._row_to_vault(r) for r in rows]

    def rename_vault(self, old_vault_id: str, new_vault_id: str) -> None:
        conn = self._connect()
        conn.execute("BEGIN IMMEDIATE")
        try:
            cur = conn.execute(
                "UPDATE vaults SET vault_id = ? WHERE vault_id = ?",
                (new_vault_id, old_vault_id),
            )
            if cur.rowcount == 0:
                conn.execute("ROLLBACK")
                raise VaultRegistrationError(
                    f"rename failed: vault_id={old_vault_id!r} not found"
                )
            conn.execute("COMMIT")
        except sqlite3.IntegrityError as e:
            conn.execute("ROLLBACK")
            raise VaultRegistrationError(
                f"rename {old_vault_id!r} → {new_vault_id!r} failed: {e}"
            ) from e

    def get_vault_by_root_path(self, root_path: Path) -> Vault | None:
        row = self._connect().execute(
            "SELECT vault_id, name, root_path, schema_version, registered_at, "
            "config_json, notes FROM vaults WHERE root_path = ?",
            (str(root_path),),
        ).fetchone()
        if row is None:
            return None
        return self._row_to_vault(row)

    @staticmethod
    def _row_to_vault(row: sqlite3.Row) -> Vault:
        """Hydrate a Vault dataclass from a sqlite3.Row."""
        config_json_raw = row["config_json"]
        config = json.loads(config_json_raw) if config_json_raw else None
        return Vault(
            vault_id=row["vault_id"],
            name=row["name"],
            root_path=Path(row["root_path"]),
            schema_version=row["schema_version"],
            registered_at=datetime.fromisoformat(row["registered_at"]),
            config_json=config,
            notes=row["notes"],
        )

