from __future__ import annotations

import hashlib
import importlib.metadata
import math
import shutil
import sqlite3
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

import numpy as np
import sqlite_vec
from numpy.typing import NDArray

VECTOR_DIMENSION = 512
VECTOR_DATABASE_NAME = "vectors.sqlite3"
DEFAULT_VECTOR_TOP_K = 30
MAX_VECTOR_TOP_K = 30


class VectorStoreError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class VectorStoreCandidate:
    """A verified sqlite-vec row before application-level scope mapping."""

    vector_store_record_id: str
    chunk_id: str
    vector_hash: str
    distance: float


class SqliteVecAdapter:
    """Persists one version-isolated 512-dimensional vector set per index version."""

    def __init__(self, vectors_root: Path, *, dimension: int = VECTOR_DIMENSION) -> None:
        if dimension != VECTOR_DIMENSION:
            raise ValueError("The frozen sqlite-vec store requires 512 dimensions.")
        self._root = vectors_root.expanduser().resolve()
        self._dimension = dimension
        self.version = importlib.metadata.version("sqlite-vec")

    @staticmethod
    def vector_hash(vector: NDArray[np.float32] | list[float]) -> str:
        values = np.asarray(vector, dtype="<f4")
        if values.shape != (VECTOR_DIMENSION,) or not np.isfinite(values).all():
            raise VectorStoreError("VECTOR_DIMENSION_OR_VALUE_INVALID")
        return hashlib.sha256(values.tobytes(order="C")).hexdigest()

    def upsert(
        self,
        *,
        embedding_config_id: str,
        index_version_id: str,
        vector_store_record_id: str,
        chunk_id: str,
        vector: NDArray[np.float32] | list[float],
        expected_hash: str,
    ) -> None:
        values = np.asarray(vector, dtype="<f4")
        actual_hash = self.vector_hash(values)
        if actual_hash != expected_hash:
            raise VectorStoreError("VECTOR_HASH_MISMATCH")
        norm = float(np.linalg.norm(values))
        if not math.isfinite(norm) or abs(norm - 1.0) > 1e-4:
            raise VectorStoreError("VECTOR_NORMALIZATION_INVALID")
        connection = self._connect(embedding_config_id, index_version_id)
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT row_id, vector_hash, chunk_id FROM vector_metadata "
                "WHERE vector_store_record_id = ?",
                (vector_store_record_id,),
            ).fetchone()
            if existing is not None:
                row_id, stored_hash, stored_chunk_id = existing
                raw = connection.execute(
                    "SELECT embedding FROM vectors WHERE rowid = ?", (row_id,)
                ).fetchone()
                if raw is None or self._blob_hash(raw[0]) != stored_hash:
                    raise VectorStoreError("VECTOR_STORE_INCONSISTENT")
                if stored_hash != expected_hash or stored_chunk_id != chunk_id:
                    raise VectorStoreError("VECTOR_RECORD_CONFLICT")
                connection.commit()
                return

            row_id = int(
                connection.execute(
                    "SELECT COALESCE(MAX(row_id), 0) + 1 FROM vector_metadata"
                ).fetchone()[0]
            )
            encoded = sqlite_vec.serialize_float32(values.tolist())
            connection.execute(
                "INSERT INTO vectors(rowid, embedding) VALUES (?, ?)", (row_id, encoded)
            )
            connection.execute(
                "INSERT INTO vector_metadata "
                "(row_id, vector_store_record_id, chunk_id, vector_hash) VALUES (?, ?, ?, ?)",
                (row_id, vector_store_record_id, chunk_id, expected_hash),
            )
            connection.commit()
        except VectorStoreError:
            connection.rollback()
            raise
        except (sqlite3.Error, ValueError, OverflowError):
            connection.rollback()
            raise VectorStoreError("VECTOR_STORE_WRITE_FAILED") from None
        finally:
            connection.close()

    def get(
        self,
        *,
        embedding_config_id: str,
        index_version_id: str,
        vector_store_record_id: str,
    ) -> tuple[NDArray[np.float32], str, str] | None:
        database = self._existing_database(embedding_config_id, index_version_id)
        if database is None:
            return None
        connection = self._connect(embedding_config_id, index_version_id)
        try:
            row = connection.execute(
                "SELECT row_id, chunk_id, vector_hash FROM vector_metadata "
                "WHERE vector_store_record_id = ?",
                (vector_store_record_id,),
            ).fetchone()
            if row is None:
                return None
            row_id, chunk_id, expected_hash = row
            stored = connection.execute(
                "SELECT embedding FROM vectors WHERE rowid = ?", (row_id,)
            ).fetchone()
            if stored is None:
                raise VectorStoreError("VECTOR_STORE_INCONSISTENT")
            raw = bytes(stored[0])
            actual_hash = self._blob_hash(raw)
            if actual_hash != expected_hash or len(raw) != self._dimension * 4:
                raise VectorStoreError("VECTOR_STORE_INCONSISTENT")
            return np.frombuffer(raw, dtype="<f4").copy(), str(chunk_id), actual_hash
        except VectorStoreError:
            raise
        except sqlite3.Error:
            raise VectorStoreError("VECTOR_STORE_READ_FAILED") from None
        finally:
            connection.close()

    def exists(
        self,
        *,
        embedding_config_id: str,
        index_version_id: str,
        vector_store_record_id: str,
        expected_hash: str | None = None,
    ) -> bool:
        result = self.get(
            embedding_config_id=embedding_config_id,
            index_version_id=index_version_id,
            vector_store_record_id=vector_store_record_id,
        )
        if result is None:
            return False
        if expected_hash is not None and result[2] != expected_hash:
            raise VectorStoreError("VECTOR_HASH_MISMATCH")
        return True

    def search(
        self,
        *,
        embedding_config_id: str,
        index_version_id: str,
        query_vector: NDArray[np.float32] | list[float],
        allowed_record_ids: Collection[str] | None = None,
        k: int = DEFAULT_VECTOR_TOP_K,
    ) -> list[VectorStoreCandidate]:
        """Return exact Top-K rows after applying the supplied record scope.

        sqlite-vec's KNN ``k`` is evaluated before a JOIN or a metadata WHERE
        clause.  The version databases currently have no dynamic partition key,
        so this method asks sqlite-vec for every stored row, filters the allowed
        record IDs in memory, and only then sorts/truncates.  This is exact for
        the current stage and intentionally has O(N) query cost.
        """
        query = self._validate_query_vector(query_vector)
        limit = self._validate_top_k(k)
        allowed = None if allowed_record_ids is None else {str(value) for value in allowed_record_ids}
        if allowed is not None and not allowed:
            return []

        database = self._existing_database(embedding_config_id, index_version_id)
        if database is None:
            return []
        connection = self._connect(embedding_config_id, index_version_id)
        try:
            vector_count = int(connection.execute("SELECT count(*) FROM vectors").fetchone()[0])
            metadata_rows = connection.execute(
                "SELECT row_id, vector_store_record_id, chunk_id, vector_hash "
                "FROM vector_metadata"
            ).fetchall()
            raw_rows = connection.execute("SELECT rowid, embedding FROM vectors").fetchall()
            if len(metadata_rows) != vector_count or len(raw_rows) != vector_count:
                raise VectorStoreError("VECTOR_STORE_INCONSISTENT")
            metadata_by_row_id = {int(row[0]): row for row in metadata_rows}
            raw_by_row_id = {int(row[0]): bytes(row[1]) for row in raw_rows}
            if len(metadata_by_row_id) != vector_count or set(metadata_by_row_id) != set(raw_by_row_id):
                raise VectorStoreError("VECTOR_STORE_INCONSISTENT")
            if vector_count == 0:
                return []

            encoded = sqlite_vec.serialize_float32(query.tolist())
            rows = connection.execute(
                "SELECT rowid, distance FROM vectors "
                "WHERE embedding MATCH ? AND k = ?",
                (encoded, vector_count),
            ).fetchall()
            if len(rows) != vector_count:
                raise VectorStoreError("VECTOR_STORE_INCONSISTENT")

            candidates: list[VectorStoreCandidate] = []
            for row_id_raw, distance_raw in rows:
                row_id = int(row_id_raw)
                metadata = metadata_by_row_id.get(row_id)
                raw = raw_by_row_id.get(row_id)
                if metadata is None or raw is None or len(raw) != self._dimension * 4:
                    raise VectorStoreError("VECTOR_STORE_INCONSISTENT")
                vector_store_record_id = str(metadata[1])
                if allowed is not None and vector_store_record_id not in allowed:
                    continue
                values = np.frombuffer(raw, dtype="<f4")
                norm = float(np.linalg.norm(values))
                if not np.isfinite(values).all() or not math.isfinite(norm) or abs(norm - 1.0) > 1e-4:
                    raise VectorStoreError("VECTOR_STORE_INCONSISTENT")
                actual_hash = self._blob_hash(raw)
                if actual_hash != str(metadata[3]):
                    raise VectorStoreError("VECTOR_STORE_INCONSISTENT")
                distance = float(distance_raw)
                if not math.isfinite(distance) or distance < 0:
                    raise VectorStoreError("VECTOR_STORE_INCONSISTENT")
                candidates.append(
                    VectorStoreCandidate(
                        vector_store_record_id=vector_store_record_id,
                        chunk_id=str(metadata[2]),
                        vector_hash=actual_hash,
                        distance=distance,
                    )
                )
            candidates.sort(key=lambda candidate: (candidate.distance, candidate.vector_store_record_id))
            return candidates[:limit]
        except VectorStoreError:
            raise
        except (sqlite3.Error, TypeError, ValueError, OverflowError):
            raise VectorStoreError("VECTOR_STORE_READ_FAILED") from None
        finally:
            connection.close()

    def query(self, **kwargs: object) -> list[VectorStoreCandidate]:
        """Compatibility alias for the internal Adapter query contract."""
        return self.search(**kwargs)  # type: ignore[arg-type]

    def delete(
        self,
        *,
        embedding_config_id: str,
        index_version_id: str,
        vector_store_record_id: str,
    ) -> bool:
        database = self._existing_database(embedding_config_id, index_version_id)
        if database is None:
            return False
        connection = self._connect(embedding_config_id, index_version_id)
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT row_id FROM vector_metadata WHERE vector_store_record_id = ?",
                (vector_store_record_id,),
            ).fetchone()
            if row is None:
                connection.commit()
                return False
            connection.execute("DELETE FROM vectors WHERE rowid = ?", (row[0],))
            connection.execute("DELETE FROM vector_metadata WHERE row_id = ?", (row[0],))
            connection.commit()
            return True
        except sqlite3.Error:
            connection.rollback()
            raise VectorStoreError("VECTOR_STORE_DELETE_FAILED") from None
        finally:
            connection.close()

    def delete_version(self, embedding_config_id: str, index_version_id: str) -> bool:
        directory = self._version_directory(embedding_config_id, index_version_id)
        if not directory.exists():
            return False
        if directory.is_symlink() or not directory.resolve().is_relative_to(self._root):
            raise VectorStoreError("VECTOR_STORE_PATH_UNSAFE")
        try:
            shutil.rmtree(directory)
        except OSError:
            raise VectorStoreError("VECTOR_STORE_DELETE_FAILED") from None
        return True

    def list_record_ids(self, embedding_config_id: str, index_version_id: str) -> set[str]:
        database = self._existing_database(embedding_config_id, index_version_id)
        if database is None:
            return set()
        connection = self._connect(embedding_config_id, index_version_id)
        try:
            return {
                str(row[0])
                for row in connection.execute(
                    "SELECT vector_store_record_id FROM vector_metadata"
                ).fetchall()
            }
        except sqlite3.Error:
            raise VectorStoreError("VECTOR_STORE_READ_FAILED") from None
        finally:
            connection.close()

    def validate_version(
        self,
        embedding_config_id: str,
        index_version_id: str,
        *,
        allowed_records: Mapping[str, tuple[str, str]],
        required_record_ids: set[str],
    ) -> None:
        """Verify persisted vector rows against business mappings without recomputing."""
        database = self._existing_database(embedding_config_id, index_version_id)
        if database is None:
            if required_record_ids:
                raise VectorStoreError("VECTOR_STORE_RECORD_MISSING")
            return

        connection = self._connect(embedding_config_id, index_version_id)
        try:
            integrity = connection.execute("PRAGMA quick_check").fetchone()
            if integrity is None or integrity[0] != "ok":
                raise VectorStoreError("VECTOR_STORE_INTEGRITY_FAILED")

            metadata_rows = connection.execute(
                "SELECT row_id, vector_store_record_id, chunk_id, vector_hash "
                "FROM vector_metadata ORDER BY row_id"
            ).fetchall()
            vector_rows = connection.execute(
                "SELECT rowid, embedding FROM vectors ORDER BY rowid"
            ).fetchall()
            metadata_by_row = {int(row[0]): row for row in metadata_rows}
            vectors_by_row = {int(row[0]): bytes(row[1]) for row in vector_rows}
            if len(metadata_by_row) != len(metadata_rows) or set(metadata_by_row) != set(
                vectors_by_row
            ):
                raise VectorStoreError("VECTOR_STORE_MAPPING_INCONSISTENT")

            actual_ids: set[str] = set()
            for row_id, record_id_value, chunk_id_value, stored_hash_value in metadata_rows:
                record_id = str(record_id_value)
                chunk_id = str(chunk_id_value)
                stored_hash = str(stored_hash_value)
                expected = allowed_records.get(record_id)
                if expected is None or expected != (chunk_id, stored_hash):
                    raise VectorStoreError("VECTOR_STORE_MAPPING_INCONSISTENT")

                raw = vectors_by_row[int(row_id)]
                values = np.frombuffer(raw, dtype="<f4")
                actual_hash = self._blob_hash(raw)
                if (
                    len(raw) != self._dimension * 4
                    or values.shape != (self._dimension,)
                    or not np.isfinite(values).all()
                    or abs(float(np.linalg.norm(values)) - 1.0) > 1e-4
                    or actual_hash != stored_hash
                ):
                    raise VectorStoreError("VECTOR_STORE_CONTENT_INCONSISTENT")
                actual_ids.add(record_id)

            if not required_record_ids.issubset(actual_ids):
                raise VectorStoreError("VECTOR_STORE_RECORD_MISSING")
        except VectorStoreError:
            raise
        except (sqlite3.Error, TypeError, ValueError, OverflowError):
            raise VectorStoreError("VECTOR_STORE_READ_FAILED") from None
        finally:
            connection.close()

    def _connect(self, embedding_config_id: str, index_version_id: str) -> sqlite3.Connection:
        directory = self._version_directory(embedding_config_id, index_version_id)
        self._safe_directory(directory)
        connection: sqlite3.Connection | None = None
        try:
            directory.mkdir(parents=True, exist_ok=True)
            database = directory / VECTOR_DATABASE_NAME
            if database.is_symlink():
                raise VectorStoreError("VECTOR_STORE_PATH_UNSAFE")
            connection = sqlite3.connect(database, timeout=5)
            connection.enable_load_extension(True)
            try:
                sqlite_vec.load(connection)
            finally:
                connection.enable_load_extension(False)
            connection.execute("PRAGMA busy_timeout = 5000")
            connection.execute(
                f"CREATE VIRTUAL TABLE IF NOT EXISTS vectors USING vec0(embedding float[{self._dimension}])"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS vector_metadata ("
                "row_id INTEGER PRIMARY KEY, vector_store_record_id TEXT NOT NULL UNIQUE, "
                "chunk_id TEXT NOT NULL, vector_hash TEXT NOT NULL)"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS vector_store_identity ("
                "singleton INTEGER PRIMARY KEY CHECK(singleton = 1), "
                "embedding_config_id TEXT NOT NULL, index_version_id TEXT NOT NULL, "
                "dimension INTEGER NOT NULL, sqlite_vec_version TEXT NOT NULL)"
            )
            identity = connection.execute(
                "SELECT embedding_config_id, index_version_id, dimension, sqlite_vec_version "
                "FROM vector_store_identity WHERE singleton = 1"
            ).fetchone()
            expected_identity = (
                embedding_config_id,
                index_version_id,
                self._dimension,
                self.version,
            )
            if identity is None:
                connection.execute(
                    "INSERT INTO vector_store_identity "
                    "(singleton, embedding_config_id, index_version_id, dimension, sqlite_vec_version) "
                    "VALUES (1, ?, ?, ?, ?)",
                    expected_identity,
                )
            elif tuple(identity) != expected_identity:
                raise VectorStoreError("VECTOR_STORE_IDENTITY_MISMATCH")
            connection.commit()
            return connection
        except VectorStoreError:
            if connection is not None:
                connection.close()
            raise
        except Exception:
            if connection is not None:
                connection.close()
            raise VectorStoreError("VECTOR_STORE_UNAVAILABLE") from None

    @staticmethod
    def _validate_top_k(k: int) -> int:
        if isinstance(k, bool) or not isinstance(k, int) or not 1 <= k <= MAX_VECTOR_TOP_K:
            raise VectorStoreError("VECTOR_TOP_K_INVALID")
        return k

    @staticmethod
    def _validate_query_vector(vector: NDArray[np.float32] | list[float]) -> NDArray[np.float32]:
        try:
            values = np.asarray(vector, dtype="<f4")
        except (TypeError, ValueError):
            raise VectorStoreError("VECTOR_QUERY_INVALID") from None
        if values.shape != (VECTOR_DIMENSION,) or not np.isfinite(values).all():
            raise VectorStoreError("VECTOR_QUERY_INVALID")
        norm = float(np.linalg.norm(values))
        if not math.isfinite(norm) or abs(norm - 1.0) > 1e-4:
            raise VectorStoreError("VECTOR_QUERY_NOT_NORMALIZED")
        return values

    def _existing_database(self, embedding_config_id: str, index_version_id: str) -> Path | None:
        directory = self._version_directory(embedding_config_id, index_version_id)
        self._safe_directory(directory)
        database = directory / VECTOR_DATABASE_NAME
        if database.is_symlink():
            raise VectorStoreError("VECTOR_STORE_PATH_UNSAFE")
        return database if database.is_file() else None

    def _version_directory(self, embedding_config_id: str, index_version_id: str) -> Path:
        try:
            config_segment = str(UUID(embedding_config_id))
            version_segment = str(UUID(index_version_id))
        except (AttributeError, TypeError, ValueError):
            raise VectorStoreError("VECTOR_STORE_PATH_UNSAFE") from None
        return self._root / config_segment / version_segment

    def _safe_directory(self, directory: Path) -> None:
        if self._root.is_symlink():
            raise VectorStoreError("VECTOR_STORE_PATH_UNSAFE")
        current = self._root
        for part in directory.relative_to(self._root).parts:
            current = current / part
            if current.is_symlink():
                raise VectorStoreError("VECTOR_STORE_PATH_UNSAFE")
        if not directory.resolve().is_relative_to(self._root):
            raise VectorStoreError("VECTOR_STORE_PATH_UNSAFE")

    @staticmethod
    def _blob_hash(blob: bytes | memoryview) -> str:
        return hashlib.sha256(bytes(blob)).hexdigest()
