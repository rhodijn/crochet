#!/usr/bin/env python3

from app.services.skkg_service import search


def search_objects(query: str, limit: int = 12) -> list[dict]:
    """Search SKKG and convert the result into dicts the templates use.
    Raises requests exceptions if the SPARQL endpoint is not reachable."""
    query = query.strip()
    if not query:
        return []
    data = search(query, limit=limit)
    return [
        {
            "id": uri,
            "title": item["title"] or "Untitled object",
            "description": item["match"],
            "image_url": None,  # TODO backend: fill from the IIIF manifest
        }
        for uri, item in data["results"].items()
    ]