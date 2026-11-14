"""
Search the local SQLite snapshot of the SKKG collection (app/data/skkg.db).
The file is created once with:  python scripts/build_skkg_db.py
"""
import sqlite3
from contextlib import closing
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "skkg.db"

SEARCH_FIELDS = ["werktitel", "kuenstler", "gattung", "material", "schlagwoerter"]
MAX_TERMS = 5

# Artworks shown as examples on the start page. Replace with your own picks.
FEATURED_OBJECT_IDS = [
    "11880",                                  # Hodler, Schwinger
    "0ff57e16-64cc-475b-aacc-d0cab9a42d1e",   # Hodler, Studie zu «Der Auserwählte»
    "10044",                                  # Hodler, Rückzug von Marignano
    "1682",                                   # Hodler, Mondschein am Genfersee
]

SCHEMA = """
CREATE TABLE artworks (
    id            TEXT PRIMARY KEY,
    uri           TEXT NOT NULL,
    title         TEXT,
    artists       TEXT,
    date          TEXT,
    gattung       TEXT,
    material      TEXT,
    schlagwoerter TEXT
);
-- one row per searchable value, already lowercased
CREATE TABLE search_terms (
    artwork_id TEXT NOT NULL REFERENCES artworks(id),
    field      TEXT NOT NULL,
    text       TEXT NOT NULL
);
CREATE INDEX idx_search_terms_field ON search_terms(field);
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
"""

COLUMNS = "id, uri, title, artists, date, gattung, material, schlagwoerter"


def connect() -> sqlite3.Connection:
    if not DB_PATH.exists():
        raise FileNotFoundError(
            f"{DB_PATH} does not exist. Build it with: python scripts/build_skkg_db.py"
        )
    connection = sqlite3.connect(DB_PATH.as_uri() + "?mode=ro", uri=True)  # read-only
    connection.row_factory = sqlite3.Row
    return connection


def _like_pattern(term: str) -> str:
    """Lowercase and escape % and _ so they are searched literally."""
    escaped = term.lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def search(keyword: str, limit: int = 20, offset: int = 0, fields: list = None) -> dict:
    """Every word must appear in at least one of the fields (default: all)."""
    terms = list(dict.fromkeys(keyword.split()))[:MAX_TERMS]
    if not terms:
        raise ValueError("Give at least one search term.")

    fields = fields or SEARCH_FIELDS
    unknown = set(fields) - set(SEARCH_FIELDS)
    if unknown:
        raise ValueError(
            f"Unknown field(s): {', '.join(sorted(unknown))}. "
            f"Available: {', '.join(SEARCH_FIELDS)}"
        )

    field_marks = ",".join("?" * len(fields))
    conditions, params = [], []
    for term in terms:
        conditions.append(
            f"id IN (SELECT artwork_id FROM search_terms "
            f"WHERE field IN ({field_marks}) AND text LIKE ? ESCAPE '\\')"
        )
        params += [*fields, _like_pattern(term)]
    where = " AND ".join(conditions)

    with closing(connect()) as connection:
        total = connection.execute(
            f"SELECT COUNT(*) FROM artworks WHERE {where}", params
        ).fetchone()[0]
        rows = connection.execute(
            f"SELECT {COLUMNS} FROM artworks WHERE {where} "
            f"ORDER BY title COLLATE NOCASE LIMIT ? OFFSET ?",
            [*params, limit, offset],
        ).fetchall()

    results = [dict(row) for row in rows]
    return {
        "keyword": keyword,
        "terms": terms,
        "fields": fields,
        "limit": limit,
        "offset": offset,
        "total": total,
        "count": len(results),
        "has_more": offset + len(results) < total,
        "results": results,
    }


def get_featured() -> list:
    """The example artworks, in the order of FEATURED_OBJECT_IDS."""
    marks = ",".join("?" * len(FEATURED_OBJECT_IDS))
    with closing(connect()) as connection:
        rows = connection.execute(
            f"SELECT {COLUMNS} FROM artworks WHERE id IN ({marks})", FEATURED_OBJECT_IDS
        ).fetchall()
    by_id = {row["id"]: dict(row) for row in rows}
    return [by_id[i] for i in FEATURED_OBJECT_IDS if i in by_id]


def get_artwork(object_id: str):
    """One artwork by its id, or None."""
    with closing(connect()) as connection:
        row = connection.execute(
            f"SELECT {COLUMNS} FROM artworks WHERE id = ?", (object_id,)
        ).fetchone()
    return dict(row) if row else None