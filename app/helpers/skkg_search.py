"""
Search the SKKG "Sammlung digital" via its public SPARQL endpoint
and get the results back as a Python dictionary.

Usage:
    from skkg_search import search

    results = search("Hodler")
    results = search("Uhr", "Silber")                    # both terms must match
    results = search("Armbrust", fields=["names"], limit=200)

Requires: pip install requests
"""
import re, requests

from app.config.settings import Settings

config: Settings = Settings()


def regex_literal(term: str) -> str:
    """Escape a plain search term for use inside a SPARQL REGEX string literal."""
    escaped = re.sub(r'([\\.^$|?*+()\[\]{}])', r"\\\1", term)  # regex metacharacters
    return escaped.replace("\\", "\\\\").replace('"', '\\"')    # string-literal escaping


def build_query(terms, fields, limit, obj_type):
    blocks = []
    for i, term in enumerate(terms):
        var = f"?t{i}"
        unions = " UNION ".join(f"{{ ?obj {config.SKKG_TEXT_PATHS[f]} {var} }}" for f in fields)
        blocks.append(
            f"  {unions}\n"
            f'  FILTER(REGEX(STR({var}), "{regex_literal(term)}", "i"))'
        )
    type_line = f"  ?obj a {obj_type} .\n" if obj_type else ""

    return f"""{config.SKKG_PREFIXES}
SELECT ?obj (SAMPLE(?label) AS ?title) (SAMPLE(?name) AS ?altTitle) (SAMPLE(?t0) AS ?match)
WHERE {{
{type_line}{chr(10).join(blocks)}
  OPTIONAL {{ ?obj rdfs:label ?label }}
  OPTIONAL {{ ?obj {config.SKKG_TEXT_PATHS["names"]} ?name }}
}}
GROUP BY ?obj
LIMIT {limit}
"""


def search(*terms, fields=None, limit=10, obj_type=config.SKKG_DEFAULT_TYPE, timeout=60):
    """
    Search the collection and return a dictionary:

        {
            "terms":   ["Hodler"],
            "count":   2,
            "query":   "<the SPARQL that was run>",
            "results": {
                "<object URI>": {"title": "...", "match": "..."},
                ...
            },
        }

    terms     one or more search terms; all must match (AND), case-insensitive
    fields    any of "labels", "names", "descriptions" (default: all)
    limit     maximum number of objects returned
    obj_type  RDF class to restrict to; pass None to search all entity types
    """
    if not terms:
        raise ValueError("Give at least one search term.")
    fields = fields or list(config.SKKG_TEXT_PATHS)
    unknown = set(fields) - set(config.SKKG_TEXT_PATHS)
    if unknown:
        raise ValueError(f"Unknown field(s): {unknown}. Use {list(config.SKKG_TEXT_PATHS)}.")

    query = build_query(terms, fields, limit, obj_type)
    resp = requests.get(
        config.ENDPOINT,
        params={"query": query},
        headers={"Accept": "application/sparql-results+json"},
        timeout=timeout,
    )
    resp.raise_for_status()

    results = {}
    for b in resp.json()["results"]["bindings"]:
        get = lambda k: b.get(k, {}).get("value", "")
        results[get("obj")] = {
            "title": get("title") or get("altTitle"),
            "match": get("match"),
        }

    return {"terms": list(terms), "count": len(results), "query": query, "results": results}


if __name__ == "__main__":
    res = search("Hodler", limit=10)

    for k, v in res['results'].items():
        print(f"{k}: {v['title']}")