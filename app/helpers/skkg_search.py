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
import re

import requests

ENDPOINT = "https://sparql.digital.skkg.ch"

PREFIXES = """PREFIX crm: <http://www.cidoc-crm.org/cidoc-crm/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX la: <https://linked.art/ns/terms/>
"""

# Where text lives on an object in the Linked Art model.
# Adjust these paths if the SKKG graph turns out to use different ones.
TEXT_PATHS = {
    "labels": "rdfs:label",
    "names": "crm:P1_is_identified_by/crm:P190_has_symbolic_content",
    "descriptions": "crm:P67i_is_referred_to_by/crm:P190_has_symbolic_content",
}

# How an object points to its IIIF manifest (standard Linked Art pattern).
# If you get no results, open the "Objects of type 'Armbrust' and their IIIF
# Manifests" example in the QLever UI and copy the path it uses into here.
MANIFEST_PATH = "crm:P129i_is_subject_of/la:digitally_carried_by/la:access_point"

# Keeps only links that look like IIIF manifests (an object may also link to
# ordinary web pages). Set to "" to switch the check off.
MANIFEST_FILTER = 'FILTER(REGEX(STR(?manifest), "iiif|manifest", "i"))'

DEFAULT_TYPE = "crm:E22_Human-Made_Object"


def regex_literal(term: str) -> str:
    """Escape a plain search term for use inside a SPARQL REGEX string literal."""
    escaped = re.sub(r'([\\.^$|?*+()\[\]{}])', r"\\\1", term)  # regex metacharacters
    return escaped.replace("\\", "\\\\").replace('"', '\\"')    # string-literal escaping


def build_query(terms, fields, limit, obj_type):
    blocks = []
    for i, term in enumerate(terms):
        var = f"?t{i}"
        unions = " UNION ".join(f"{{ ?obj {TEXT_PATHS[f]} {var} }}" for f in fields)
        blocks.append(
            f"  {unions}\n"
            f'  FILTER(REGEX(STR({var}), "{regex_literal(term)}", "i"))'
        )
    type_line = f"  ?obj a {obj_type} .\n" if obj_type else ""

    return f"""{PREFIXES}
SELECT ?manifest ?obj (SAMPLE(?label) AS ?title) (SAMPLE(?name) AS ?altTitle) (SAMPLE(?t0) AS ?match)
WHERE {{
{type_line}{chr(10).join(blocks)}
  ?obj {MANIFEST_PATH} ?manifest .
  {MANIFEST_FILTER}
  OPTIONAL {{ ?obj rdfs:label ?label }}
  OPTIONAL {{ ?obj {TEXT_PATHS["names"]} ?name }}
}}
GROUP BY ?manifest ?obj
LIMIT {limit}
"""


def search(*terms, fields=None, limit=50, obj_type=DEFAULT_TYPE, timeout=60):
    """
    Search the collection and return a dictionary:

        {
            "terms":   ["Hodler"],
            "count":   2,
            "query":   "<the SPARQL that was run>",
            "results": {
                "<IIIF manifest URL>": {"object": "<object URI>", "title": "...", "match": "..."},
                ...
            },
        }

    terms     one or more search terms; all must match (AND), case-insensitive
    fields    any of "labels", "names", "descriptions" (default: all)
    limit     maximum number of manifests returned

    Only objects that have a IIIF manifest are returned. An object with several
    manifests appears once per manifest.
    obj_type  RDF class to restrict to; pass None to search all entity types
    """
    if not terms:
        raise ValueError("Give at least one search term.")
    fields = fields or list(TEXT_PATHS)
    unknown = set(fields) - set(TEXT_PATHS)
    if unknown:
        raise ValueError(f"Unknown field(s): {unknown}. Use {list(TEXT_PATHS)}.")

    query = build_query(terms, fields, limit, obj_type)
    resp = requests.get(
        ENDPOINT,
        params={"query": query},
        headers={"Accept": "application/sparql-results+json"},
        timeout=timeout,
    )
    resp.raise_for_status()

    results = {}
    for b in resp.json()["results"]["bindings"]:
        get = lambda k: b.get(k, {}).get("value", "")
        results[get("manifest")] = {
            "object": get("obj"),
            "title": get("title") or get("altTitle"),
            "match": get("match"),
        }

    return {"terms": list(terms), "count": len(results), "query": query, "results": results}


if __name__ == "__main__":
    res = search("bär", limit=10)

    for k, v in res['results'].items():
        print(f"{k}: {v['title']}")