"""
Download the SKKG collection once and save it as a fixed SQLite file.

    python -m scripts.build_skkg_db        (run from the project root)

Creates app/data/skkg.db. Run it again whenever you want fresh data.
"""
import os
import sqlite3
import time
from collections import defaultdict
from datetime import datetime, timezone

from app.services.skkg_db import DB_PATH, SCHEMA
from app.services.skkg_service import ARTIST_PATH, DATE_PATH, PREFIXES, object_id, run_query

PAGE_SIZE = 20_000   # lower this if SKKG reports "Operation timed out"

# (column in the artworks table, SPARQL pattern that binds ?obj and ?text)
HARVEST = [
    ("title",         "?obj skos:prefLabel ?text ."),
    ("artists",       f"?obj {ARTIST_PATH} ?m . ?m skos:prefLabel ?text ."),
    ("date",          f"?obj {DATE_PATH}/rdfs:label ?text ."),
    ("gattung",       "?obj crm:P2_has_type/skos:prefLabel ?text ."),
    ("material",      "?obj crm:P45_consists_of/skos:prefLabel ?text ."),
    ("material",      "?obj crm:P108i_was_produced_by/crm:P32_used_general_technique/skos:prefLabel ?text ."),
    ("schlagwoerter", "?obj crm:P62_depicts/skos:prefLabel ?text ."),
]

# Which columns are searchable, and under which field name (date is display only)
SEARCHABLE = {
    "title": "werktitel",
    "artists": "kuenstler",
    "gattung": "gattung",
    "material": "material",
    "schlagwoerter": "schlagwoerter",
}


def harvest(pattern: str):
    """Yield (object URI, text) for one pattern, page by page."""
    offset = 0
    while True:
        query = f"""{PREFIXES}
SELECT ?obj ?text WHERE {{
    ?obj a skkgonto:Object .
    {pattern}
}}
ORDER BY ?obj ?text
LIMIT {PAGE_SIZE}
OFFSET {offset}
"""
        rows = run_query(query, timeout=300)
        for row in rows:
            yield row["obj"]["value"], row["text"]["value"]
        print(f"    {offset + len(rows):>8} rows")
        if len(rows) < PAGE_SIZE:
            return
        offset += PAGE_SIZE


def main():
    started = time.time()
    data = defaultdict(lambda: defaultdict(list))   # uri -> column -> [values]

    for column, pattern in HARVEST:
        print(f"Downloading {column} ...")
        for uri, text in harvest(pattern):
            values = data[uri][column]
            if text not in values:
                values.append(text)

    print(f"Writing {len(data)} artworks to {DB_PATH} ...")
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = DB_PATH.with_suffix(".tmp")
    if tmp_path.exists():
        tmp_path.unlink()

    connection = sqlite3.connect(tmp_path)
    connection.executescript(SCHEMA)

    artworks, search_terms = [], []
    for uri, columns in data.items():
        obj_id = object_id(uri)
        artworks.append((
            obj_id, uri,
            "; ".join(columns["title"][:1]),          # one title is enough for display
            "; ".join(columns["artists"]),
            "; ".join(columns["date"][:1]),
            "; ".join(columns["gattung"]),
            "; ".join(columns["material"]),
            "; ".join(columns["schlagwoerter"]),
        ))
        for column, field in SEARCHABLE.items():
            for value in columns[column]:
                search_terms.append((obj_id, field, value.lower()))

    connection.executemany("INSERT INTO artworks VALUES (?, ?, ?, ?, ?, ?, ?, ?)", artworks)
    connection.executemany("INSERT INTO search_terms VALUES (?, ?, ?)", search_terms)
    connection.execute(
        "INSERT INTO meta VALUES ('created_at', ?)",
        (datetime.now(timezone.utc).isoformat(timespec="seconds"),),
    )
    connection.commit()
    connection.execute("VACUUM")
    connection.close()

    os.replace(tmp_path, DB_PATH)   # only replace the old db once the new one is complete
    print(f"Done in {time.time() - started:.0f}s: {len(artworks)} artworks, "
          f"{len(search_terms)} search values.")


if __name__ == "__main__":
    main()