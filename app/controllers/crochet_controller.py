"""
API for the 2D / 3D buttons on the detail page.

  POST /api/crochet/2d               {object_id, width?, colors?, yarn_weight?}
       -> colour chart + row instructions (always) + written tapestry pattern (needs API key)
  GET  /api/crochet/charts/<file>    -> the chart image
  POST /api/crochet/3d-instructions  {object_id, colors?, yarn_weight?}
       -> amigurumi pattern; the 3D model itself comes from /api/model3d (job + polling)

Finished patterns are saved in app/data/patterns/ and reused, so a second click is free.
"""
import json
import logging
import re
from pathlib import Path

from flask import Blueprint, jsonify, request, send_file

from app.services import skkg_db
from app.services.chart2d_service import make_chart, row_instructions, save_chart_png
from app.services.crochet_service import (
    DEFAULT_YARN, YARN_WEIGHTS, finished_size_cm, generate_instructions, get_api_key,
)
from app.services.model3d_service import describe_model, model_path
from app.services.skkg_service import get_image_urls

logger = logging.getLogger(__name__)

crochet_controller = Blueprint("crochet_controller", __name__, url_prefix="/api/crochet")

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CHARTS_DIR = DATA_DIR / "charts"
PATTERNS_DIR = DATA_DIR / "patterns"
OBJECT_ID = re.compile(r"[A-Za-z0-9-]{1,64}")
CHART_FILE = re.compile(r"[A-Za-z0-9-]{1,64}_\d{1,3}_\d{1,2}\.png")

NO_KEY_MESSAGE = ("No Anthropic API key is configured on the server, so the written pattern "
                  "is missing. The chart and row instructions are complete.")


def error(message: str, status: int):
    return jsonify({"success": False, "message": message}), status


def clamp(value, default: int, low: int, high: int) -> int:
    try:
        return max(low, min(int(value), high))
    except (TypeError, ValueError):
        return default


def yarn_choice(body: dict) -> str:
    yarn = str(body.get("yarn_weight", DEFAULT_YARN))
    return yarn if yarn in YARN_WEIGHTS else DEFAULT_YARN


def load_artwork():
    """Artwork + image URL from the request body, or an error response."""
    body = request.get_json(silent=True) or {}
    object_id = str(body.get("object_id", "")).strip()
    if not OBJECT_ID.fullmatch(object_id):
        return None, None, error("Please send a valid object_id.", 400)
    artwork = skkg_db.get_artwork(object_id)
    if not artwork:
        return None, None, error("Artwork not found.", 404)
    image_url = get_image_urls(object_id).get("image_url")
    if not image_url:
        return None, None, error("This artwork has no image.", 404)
    return artwork, image_url, None


def cached_pattern(path: Path, create):
    """Return the saved pattern, or create and save it."""
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    pattern = create()
    PATTERNS_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(pattern, ensure_ascii=False), encoding="utf-8")
    return pattern


@crochet_controller.post("/2d")
def crochet_2d():
    artwork, image_url, failed = load_artwork()
    if failed:
        return failed

    body = request.get_json(silent=True) or {}
    width = clamp(body.get("width"), 40, 20, 80)
    colors = clamp(body.get("colors"), 6, 2, 8)
    yarn = yarn_choice(body)
    name = f"{artwork['id']}_{width}_{colors}"

    try:
        chart = make_chart(image_url, width=width, colors=colors)
        CHARTS_DIR.mkdir(parents=True, exist_ok=True)
        save_chart_png(chart, CHARTS_DIR / f"{name}.png")
    except Exception:
        logger.exception("Chart failed for %s", artwork["id"])
        return error("The colour chart could not be created.", 502)

    pattern, message = None, None
    pattern_file = PATTERNS_DIR / f"{name}_{yarn}_2d.json"
    if pattern_file.exists() or get_api_key():
        try:
            pattern = cached_pattern(pattern_file, lambda: generate_instructions(
                artwork, image_url, "tapestry", chart=chart, yarn_weight=yarn, colors=colors))
        except Exception:
            logger.exception("Tapestry instructions failed for %s", artwork["id"])
            message = "The written pattern could not be generated. The chart and rows are complete."
    else:
        message = NO_KEY_MESSAGE

    width_cm, height_cm = finished_size_cm(chart["width"], chart["height"], yarn)
    return jsonify({
        "success": True,
        "chart_url": f"/api/crochet/charts/{name}.png",
        "width": chart["width"],
        "height": chart["height"],
        "size_cm": [width_cm, height_cm],
        "yarn": YARN_WEIGHTS[yarn],
        "colors": chart["colors"],
        "rows": row_instructions(chart),
        "pattern": pattern,
        "message": message,
    })


@crochet_controller.get("/charts/<file_name>")
def chart_image(file_name: str):
    if not CHART_FILE.fullmatch(file_name):
        return error("Invalid file.", 400)
    path = CHARTS_DIR / file_name
    if not path.exists():
        return error("Chart not found.", 404)
    return send_file(path, mimetype="image/png")


@crochet_controller.post("/3d-instructions")
def crochet_3d():
    artwork, image_url, failed = load_artwork()
    if failed:
        return failed

    glb = model_path(artwork["id"], "glb")
    if not glb.exists():
        return error("Generate the 3D model first.", 409)

    body = request.get_json(silent=True) or {}
    colors = clamp(body.get("colors"), 6, 2, 8)
    yarn = yarn_choice(body)
    pattern_file = PATTERNS_DIR / f"{artwork['id']}_{colors}_{yarn}_3d.json"
    if not pattern_file.exists() and not get_api_key():
        return error(NO_KEY_MESSAGE.replace(" The chart and row instructions are complete.", ""), 503)

    try:
        pattern = cached_pattern(pattern_file, lambda: generate_instructions(
            artwork, image_url, "amigurumi", model_info=describe_model(glb),
            yarn_weight=yarn, colors=colors))
    except Exception:
        logger.exception("Amigurumi instructions failed for %s", artwork["id"])
        return error("The instructions could not be generated. Please try again.", 502)

    return jsonify({"success": True, "pattern": pattern})