from __future__ import annotations

import sqlite3
from array import array

import sqlite_vec


def vector(values: list[float]) -> bytes:
    return sqlite_vec.serialize_float32(array("f", values))


def run() -> None:
    connection = sqlite3.connect(":memory:")
    connection.enable_load_extension(True)
    sqlite_vec.load(connection)
    connection.execute(
        "CREATE VIRTUAL TABLE vectors USING vec0(embedding float[512], +scope TEXT NOT NULL)"
    )
    connection.execute("CREATE TABLE vector_meta(rowid INTEGER PRIMARY KEY, scope TEXT NOT NULL)")

    base = [0.0] * 512
    near = [0.0] * 512
    near[0] = 0.9
    other_scope = [0.0] * 512
    other_scope[1] = 0.9
    connection.executemany(
        "INSERT INTO vectors(rowid, embedding, scope) VALUES (?, ?, ?)",
        [
            (1, vector(base), "knowledge-a"),
            (2, vector(near), "knowledge-a"),
            (3, vector(other_scope), "knowledge-b"),
        ],
    )
    connection.executemany(
        "INSERT INTO vector_meta(rowid, scope) VALUES (?, ?)",
        [(1, "knowledge-a"), (2, "knowledge-a"), (3, "knowledge-b")],
    )

    rows = connection.execute(
        "SELECT vectors.rowid, vectors.distance "
        "FROM vectors JOIN vector_meta ON vector_meta.rowid = vectors.rowid "
        "WHERE vectors.embedding MATCH ? AND vectors.k = 5 "
        "AND vector_meta.scope = ? ORDER BY vectors.distance",
        (vector(near), "knowledge-a"),
    ).fetchall()
    assert rows and rows[0][0] == 2, rows
    assert all(row[0] != 3 for row in rows), rows

    connection.execute("DELETE FROM vectors WHERE rowid = ?", (2,))
    connection.execute("DELETE FROM vector_meta WHERE rowid = ?", (2,))
    remaining = connection.execute("SELECT count(*) FROM vectors").fetchone()[0]
    assert remaining == 2, remaining
    print(f"sqlite-vec PASS: filtered_top_row={rows[0][0]} remaining={remaining} dimension=512")


if __name__ == "__main__":
    run()
