import logging
import re

import requests
from flask import Blueprint, jsonify, redirect, request

from app.services.skkg_db import get_featured, search
from app.services.skkg_service import get_image_urls

logger = logging.getLogger(__name__)

skkg_controller = Blueprint("skkg_controller", __name__, url_prefix="/api/skkg")


def int_arg(name: str, default: int, low: int, high: int) -> int:
    try:
        value = int(request.args.get(name, default))
    except ValueError:
        value = default
    return max(low, min(value, high))


def error(message: str, status: int):
    return jsonify({"success": False, "message": message}), status


@skkg_controller.get("/search")
def search_collection():
    keyword = request.args.get("keyword", "").strip()
    if len(keyword) < 2:
        return error("Please enter at least 2 characters.", 400)

    limit = int_arg("limit", 20, 1, 100)
    offset = int_arg("offset", 0, 0, 1_000_000)
    # Optional: ?fields=gattung,material  (default: all fields)
    fields = [f.strip() for f in request.args.get("fields", "").split(",") if f.strip()]

    try:
        return jsonify({"success": True, **search(keyword, limit, offset, fields or None)})
    except ValueError as exc:
        return error(str(exc), 400)
    except FileNotFoundError:
        logger.exception("SKKG database missing")
        return error("The artwork database has not been built yet.", 503)
    except Exception:
        logger.exception("Unexpected SKKG search error")
        return error("An unexpected error occurred.", 500)


@skkg_controller.get("/featured")
def featured_artworks():
    try:
        results = get_featured()
        return jsonify({"success": True, "count": len(results), "results": results})
    except FileNotFoundError:
        logger.exception("SKKG database missing")
        return error("The artwork database has not been built yet.", 503)


@skkg_controller.get("/image/<object_id>")
def artwork_image(object_id: str):
    """
    Redirects to the artwork's thumbnail, so the frontend can simply use
    <img src="/api/skkg/image/<id>" loading="lazy">. Add ?size=full for 1600px.
    """
    if not re.fullmatch(r"[A-Za-z0-9-]{1,64}", object_id):
        return error("Invalid object id.", 400)

    try:
        image = get_image_urls(object_id)
    except requests.RequestException:
        logger.exception("Loading image failed")
        return error("Could not retrieve the image.", 502)

    key = "image_url" if request.args.get("size") == "full" else "thumbnail_url"
    if not image.get(key):
        return error("No image available.", 404)

    response = redirect(image[key], code=302)
    response.headers["Cache-Control"] = "public, max-age=86400"
    return response