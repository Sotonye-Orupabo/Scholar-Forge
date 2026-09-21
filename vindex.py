"""Vector indexes behind one interface. Scores are cosine similarity on unit vectors."""
import array
import sqlite3
from typing import Iterable, List, Protocol, Tuple

Item = Tuple[int, int, List[float]]  # (chunk_id, doc_id, vector)


class VectorIndex(Protocol):
    def add(self, items: Iterable[Item]) -> None: ...
    def delete_doc(self, doc_id: int) -> None: ...
    def query(self, vec: List[float], k: int) -> List[Tuple[int, float]]: ...
    def clear(self) -> None: ...
    def count(self) -> int: ...


class SqliteVectorIndex:
    """Float32 blobs in SQLite, scored with numpy when available (pure Python otherwise)."""

    def __init__(self, db: sqlite3.Connection):
        self.db = db
        db.execute("CREATE TABLE IF NOT EXISTS vectors(chunk_id INTEGER PRIMARY KEY, doc_id INTEGER, vec BLOB)")

    def add(self, items):
        self.db.executemany("INSERT OR REPLACE INTO vectors(chunk_id, doc_id, vec) VALUES(?,?,?)",
                            [(c, d, array.array("f", v).tobytes()) for c, d, v in items])
        self.db.commit()

    def delete_doc(self, doc_id):
        self.db.execute("DELETE FROM vectors WHERE doc_id=?", (doc_id,))
        self.db.commit()

    def clear(self):
        self.db.execute("DELETE FROM vectors")
        self.db.commit()

    def count(self):
        return self.db.execute("SELECT COUNT(*) FROM vectors").fetchone()[0]

    def query(self, vec, k):
        rows = self.db.execute("SELECT chunk_id, vec FROM vectors").fetchall()
        if not rows:
            return []
        try:
            import numpy as np
            mat = np.frombuffer(b"".join(r[1] for r in rows), dtype=np.float32).reshape(len(rows), -1)
            scores = mat @ np.asarray(vec, dtype=np.float32)
            top = np.argsort(-scores)[:k]
            return [(rows[i][0], float(scores[i])) for i in top]
        except ImportError:
            scored = []
            for cid, blob in rows:
                a = array.array("f"); a.frombytes(blob)
                scored.append((cid, sum(x * y for x, y in zip(a, vec))))
            return sorted(scored, key=lambda t: -t[1])[:k]


class LanceVectorIndex:
    """LanceDB backend (pip install lancedb). Written against the documented Python API and not
    exercised in the build sandbox, where lancedb could not be installed. The shared contract
    tests in tests/test_vindex.py run against it automatically when lancedb is importable."""

    def __init__(self, path: str, table: str = "chunks"):
        import lancedb
        self.db, self.name, self.tbl = lancedb.connect(path), table, None
        if table in self.db.table_names():
            self.tbl = self.db.open_table(table)

    def add(self, items):
        rows = [{"chunk_id": c, "doc_id": d, "vector": [float(x) for x in v]} for c, d, v in items]
        if not rows:
            return
        if self.tbl is None:
            self.tbl = self.db.create_table(self.name, data=rows)
        else:
            self.tbl.add(rows)

    def delete_doc(self, doc_id):
        if self.tbl is not None:
            self.tbl.delete(f"doc_id = {int(doc_id)}")

    def clear(self):
        if self.tbl is not None:
            self.db.drop_table(self.name)
            self.tbl = None

    def count(self):
        return 0 if self.tbl is None else self.tbl.count_rows()

    def query(self, vec, k):
        if self.tbl is None:
            return []
        rows = self.tbl.search([float(x) for x in vec]).metric("cosine").limit(k).to_list()
        return [(int(r["chunk_id"]), 1.0 - float(r["_distance"])) for r in rows]
