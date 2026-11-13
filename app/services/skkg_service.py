"""
Search the SKKG "Sammlung digital" collection through its public SPARQL endpoint.

Data model (Linked.Art / CIDOC-CRM) as documented in:
https://github.com/swiss-art-research-net/skkg-pipeline/wiki/6.-How-to-use-the-SKKG-Linked-Data

Flow (one SPARQL request per search):
  1. matching_subquery()   -> which objects contain the keyword(s) in the search fields
  2. details_query()       -> title, artist(s), date for exactly those objects
  3. get_image_urls()      -> image + thumbnail from the IIIF manifest, loaded separately
                              per artwork via /api/skkg/image/<id> (cached)

Identical queries are cached for 10 minutes and requests are spaced out,
because the public endpoint answers with 429 when it gets too many.
"""
import threading
import time
from functools import lru_cache

import logging

import requests

from app.config.settings import Settings

logger = logging.getLogger(__name__)

config: Settings = Settings()

# Endpoint from the wiki; your Settings value wins if it exists.
ENDPOINT = getattr(config, "SKKG_ENDPOINT", None) or "https://sparql.digital.skkg.ch/"
MANIFEST_URL = "https://manifest.digital.skkg.ch/iiif/object/{}"

PREFIXES = """
PREFIX crm: <http://www.cidoc-crm.org/cidoc-crm/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
PREFIX skkgonto: <https://ontology.skkg.ch/>
"""

# Object -> production -> production part -> person   (wiki: "Objects and artists")
ARTIST_PATH = "crm:P108i_was_produced_by/crm:P9_consists_of/crm:P14_carried_out_by"
# Object -> production -> time-span                    (wiki: production date example)
DATE_PATH = "crm:P108i_was_produced_by/crm:P4_has_time-span"

# Object IDs shown as examples on the start page. Replace with your own picks.
FEATURED_OBJECT_IDS = [7543, 11880]

MAX_TERMS = 5


# ---------------------------------------------------------------- helpers

def sparql_literal(text: str) -> str:
    """Escape a plain string for use as a SPARQL string literal."""
    escaped = (
        text.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
    )
    return f'"{escaped}"'


# Be polite to the public endpoint: identify the app, space out requests,
# reuse answers for identical queries.
session = requests.Session()
session.headers.update({
    "Accept": "application/sparql-results+json",
    "User-Agent": "crochet-skkg-search/1.0 (student project)",
})

MIN_SECONDS_BETWEEN_REQUESTS = 1.0
CACHE_SECONDS = 10 * 60
MAX_CACHE_ENTRIES = 500

_query_cache: dict = {}          # query -> (timestamp, bindings)
_throttle_lock = threading.Lock()
_last_request_at = 0.0


def _wait_for_turn() -> None:
    """Allow at most one request per MIN_SECONDS_BETWEEN_REQUESTS."""
    global _last_request_at
    with _throttle_lock:
        wait = _last_request_at + MIN_SECONDS_BETWEEN_REQUESTS - time.time()
        if wait > 0:
            time.sleep(wait)
        _last_request_at = time.time()


def run_query(query: str, timeout: int = 60) -> list:
    cached = _query_cache.get(query)
    if cached and time.time() - cached[0] < CACHE_SECONDS:
        return cached[1]

    for attempt in range(2):
        _wait_for_turn()
        response = session.get(ENDPOINT, params={"query": query}, timeout=timeout)

        if response.status_code == 429 and "timed out" in response.text:
            # Not a rate limit: the query itself was too slow. Retrying won't help.
            logger.warning("SKKG query timed out:\n%s", query)
            raise requests.Timeout("SKKG query timed out")

        if response.status_code == 429 and attempt == 0:
            # Retry once, after the time the server asks for (max 10 s).
            try:
                retry_after = int(response.headers.get("Retry-After", 3))
            except ValueError:
                retry_after = 3
            time.sleep(min(retry_after, 10))
            continue
        break

    if not response.ok:
        # QLever explains what went wrong in the body (bad query, timeout, ...)
        logger.error(
            "SKKG endpoint returned %s:\n%s\n--- query ---\n%s",
            response.status_code, response.text[:2000], query,
        )
    response.raise_for_status()
    bindings = response.json()["results"]["bindings"]

    if len(_query_cache) >= MAX_CACHE_ENTRIES:
        _query_cache.pop(next(iter(_query_cache)))   # drop the oldest entry
    _query_cache[query] = (time.time(), bindings)
    return bindings


def object_id(uri: str) -> str:
    return uri.rstrip("/").split("/")[-1]


# ---------------------------------------------------------------- step 1: matching

# Searchable fields. Every pattern first finds the labels that contain the
# keyword ({t} + filter {f}) and only then follows the link to the artwork.
# Filtering first keeps the query fast; the other way round SKKG times out.
#   {t} = the label text, {f} = the keyword filter, ?m{i} = the matched entity
SEARCH_FIELDS = {
    "werktitel": [
        "?obj skos:prefLabel {t} . {f}",
    ],
    "kuenstler": [
        "?m{i} skos:prefLabel {t} . {f} ?obj " + ARTIST_PATH + " ?m{i} .",
    ],
    "gattung": [
        "?m{i} skos:prefLabel {t} . {f} ?obj crm:P2_has_type ?m{i} .",
    ],
    "material": [
        "?m{i} skos:prefLabel {t} . {f} ?obj crm:P45_consists_of ?m{i} .",
        "?m{i} skos:prefLabel {t} . {f} "
        "?obj crm:P108i_was_produced_by/crm:P32_used_general_technique ?m{i} .",
    ],
    "schlagwoerter": [
        "?m{i} skos:prefLabel {t} . {f} ?obj crm:P62_depicts ?m{i} .",
    ],
}


def term_block(i: int, term: str, fields: list) -> str:
    """One search term must appear in at least one of the selected fields."""
    text = f"?text{i}"
    keyword_filter = f"FILTER(CONTAINS(LCASE(STR({text})), {sparql_literal(term.lower())}))"
    patterns = [
        pattern.format(t=text, f=keyword_filter, i=i)
        for field in fields
        for pattern in SEARCH_FIELDS[field]
    ]
    unions = "\n        UNION\n        ".join(f"{{ {p} }}" for p in patterns)
    return f"""
    {{
        {unions}
    }}"""


def matching_subquery(terms: list, fields: list, limit: int, offset: int) -> str:
    """Selects the object URIs where every term matches in one of the fields (AND)."""
    blocks = "\n".join(term_block(i, t, fields) for i, t in enumerate(terms))
    return f"""
    {{
        SELECT DISTINCT ?obj WHERE {{
            ?obj a skkgonto:Object .
            {blocks}
        }}
        ORDER BY ?obj
        LIMIT {limit}
        OFFSET {offset}
    }}"""


# ---------------------------------------------------------------- step 2: details

def details_query(selection: str) -> str:
    """Title, artists and date for the objects chosen by `selection`."""
    return f"""{PREFIXES}
SELECT ?obj
       (SAMPLE(?label) AS ?title)
       (GROUP_CONCAT(DISTINCT ?artistName; SEPARATOR="; ") AS ?artists)
       (SAMPLE(?dateLabel) AS ?date)
WHERE {{
    {selection}
    OPTIONAL {{ ?obj skos:prefLabel ?label }}
    OPTIONAL {{ ?obj {ARTIST_PATH}/skos:prefLabel ?artistName }}
    OPTIONAL {{ ?obj {DATE_PATH}/rdfs:label ?dateLabel }}
}}
GROUP BY ?obj
ORDER BY ?obj
"""


def to_results(bindings: list) -> list:
    results = []
    for b in bindings:
        get = lambda key: b.get(key, {}).get("value", "")
        uri = get("obj")
        results.append({
            "id": object_id(uri),
            "uri": uri,
            "title": get("title"),
            "artists": get("artists"),
            "date": get("date"),
        })
    return results


def fetch_details(uris: list) -> list:
    """Details for a fixed list of object URIs (used for the featured artworks)."""
    if not uris:
        return []
    values = " ".join(f"<{uri}>" for uri in uris)
    return to_results(run_query(details_query(f"VALUES ?obj {{ {values} }}")))


# ---------------------------------------------------------------- step 3: images

_image_cache: dict = {}


def _image_from_body(body: dict) -> dict:
    """Full image URL plus a 400px thumbnail from the IIIF image service."""
    image = body.get("id") or body.get("@id")
    if not image:
        return {}
    thumb = image
    service = body.get("service") or []
    if isinstance(service, dict):
        service = [service]
    if service:
        service_id = service[0].get("id") or service[0].get("@id")
        if service_id:
            thumb = f"{service_id.rstrip('/')}/full/!400,400/0/default.jpg"
    return {"image_url": image, "thumbnail_url": thumb}


def _first_image(manifest: dict) -> dict:
    # IIIF v3: items -> annotation pages -> annotations -> body
    for canvas in manifest.get("items", []):
        for page in canvas.get("items", []):
            for annotation in page.get("items", []):
                body = annotation.get("body", {})
                if isinstance(body, list):
                    body = body[0] if body else {}
                found = _image_from_body(body)
                if found:
                    return found
    # IIIF v2: sequences -> canvases -> images -> resource
    for sequence in manifest.get("sequences", []):
        for canvas in sequence.get("canvases", []):
            for image in canvas.get("images", []):
                found = _image_from_body(image.get("resource", {}))
                if found:
                    return found
    return {}


def get_image_urls(obj_id: str) -> dict:
    """First image of the object's IIIF manifest (v2 or v3), cached."""
    if obj_id in _image_cache:
        return _image_cache[obj_id]

    empty = {"image_url": None, "thumbnail_url": None}
    url = MANIFEST_URL.format(obj_id)
    try:
        response = session.get(url, headers={"Accept": "application/json"}, timeout=20)
        if response.status_code == 404:
            _image_cache[obj_id] = empty      # object has no images
            return empty
        response.raise_for_status()
        manifest = response.json()
    except (requests.RequestException, ValueError) as exc:
        logger.warning("Could not load IIIF manifest %s: %s", url, exc)
        return empty                          # not cached, retried next time

    result = _first_image(manifest) or empty
    if result is empty:
        logger.info("No image found in manifest %s", url)
    _image_cache[obj_id] = result
    return result


# ---------------------------------------------------------------- public API

def search(keyword: str, limit: int = 20, offset: int = 0, fields: list = None) -> dict:
    """
    Every word of the keyword must match (e.g. "Hunde Forestier"),
    each word in at least one of the fields (default: all fields).
    Returns a list so the frontend keeps the order.
    """
    terms = list(dict.fromkeys(keyword.split()))[:MAX_TERMS]
    if not terms:
        raise ValueError("Give at least one search term.")

    fields = fields or list(SEARCH_FIELDS)
    unknown = set(fields) - set(SEARCH_FIELDS)
    if unknown:
        raise ValueError(
            f"Unknown field(s): {', '.join(sorted(unknown))}. "
            f"Available: {', '.join(SEARCH_FIELDS)}"
        )

    # One request: matching + details. Ask for one extra row to know
    # whether there is a next page.
    selection = matching_subquery(terms, fields, limit + 1, offset)
    results = to_results(run_query(details_query(selection)))
    has_more = len(results) > limit
    results = results[:limit]

    return {
        "keyword": keyword,
        "terms": terms,
        "fields": fields,
        "limit": limit,
        "offset": offset,
        "count": len(results),
        "has_more": has_more,
        "results": results,
    }


@lru_cache(maxsize=1)
def _featured_cached() -> tuple:
    uris = [f"https://data.skkg.ch/object/{i}" for i in FEATURED_OBJECT_IDS]
    return tuple(fetch_details(uris))


def get_featured() -> list:
    """Example artworks for the start page, cached in memory after the first call."""
    return list(_featured_cached())