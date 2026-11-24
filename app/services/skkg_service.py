"""
Live access to the SKKG "Sammlung digital":
  - run_query():      SPARQL against the public endpoint (used by scripts/build_skkg_db.py)
  - get_image_urls(): image + thumbnail from an artwork's IIIF manifest (used per request)

The search itself runs on the local SQLite snapshot, see skkg_db.py.
Data model: https://github.com/swiss-art-research-net/skkg-pipeline/wiki/6.-How-to-use-the-SKKG-Linked-Data
"""
import logging
import sqlite3
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

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

# ---------------------------------------------------------------- helpers

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


# ---------------------------------------------------------------- images (live)

# Found image addresses are saved in a small SQLite file, so each artwork is looked
# up at SKKG only once, even across restarts. Only addresses are stored, not images.
IMAGE_CACHE_PATH = Path(__file__).resolve().parent.parent / "data" / "image_cache.db"
_image_cache: dict = {}          # in-memory copy for speed
_cache_lock = threading.Lock()


def _cache_connect() -> sqlite3.Connection:
    IMAGE_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(IMAGE_CACHE_PATH, timeout=10)
    connection.execute(
        "CREATE TABLE IF NOT EXISTS images ("
        " object_id TEXT PRIMARY KEY, image_url TEXT, thumbnail_url TEXT, saved_at TEXT)"
    )
    return connection


def _cache_get(obj_id: str):
    if obj_id in _image_cache:
        return _image_cache[obj_id]
    with _cache_lock:
        connection = _cache_connect()
        try:
            row = connection.execute(
                "SELECT image_url, thumbnail_url FROM images WHERE object_id = ?", (obj_id,)
            ).fetchone()
        finally:
            connection.close()
    if row is None:
        return None
    result = {"image_url": row[0], "thumbnail_url": row[1]}
    _image_cache[obj_id] = result      # keep in memory, no need to write it again
    return result


def _cache_put(obj_id: str, result: dict) -> None:
    """Save a result. 'No image' is saved too (both None), so it is not asked again."""
    _image_cache[obj_id] = result
    with _cache_lock:
        connection = _cache_connect()
        try:
            connection.execute(
                "INSERT OR REPLACE INTO images VALUES (?, ?, ?, ?)",
                (obj_id, result["image_url"], result["thumbnail_url"],
                 datetime.now(timezone.utc).isoformat(timespec="seconds")),
            )
            connection.commit()
        finally:
            connection.close()


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
            # Ask the IIIF image server for scaled versions instead of the
            # original (often 7000+ px wide).
            base = service_id.rstrip("/")
            thumb = f"{base}/full/!400,400/0/default.jpg"
            image = f"{base}/full/!1600,1600/0/default.jpg"
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
    cached = _cache_get(obj_id)
    if cached is not None:
        return cached

    empty = {"image_url": None, "thumbnail_url": None}
    url = MANIFEST_URL.format(obj_id)
    manifest = None
    for attempt in range(2):                  # SKKG is sometimes slow: try twice
        try:
            response = session.get(url, headers={"Accept": "application/json"}, timeout=20)
            if response.status_code == 404:
                _cache_put(obj_id, empty)     # object has no images
                return empty
            response.raise_for_status()
            manifest = response.json()
            break
        except (requests.RequestException, ValueError) as exc:
            logger.warning("Could not load IIIF manifest %s (attempt %s): %s", url, attempt + 1, exc)
    if manifest is None:
        return empty                          # not cached, retried next time

    result = _first_image(manifest) or empty
    if result is empty:
        logger.info("No image found in manifest %s", url)
    _cache_put(obj_id, result)
    return result