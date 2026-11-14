import logging

from flask import Blueprint, abort, render_template, request

from app.services import skkg_db

logger = logging.getLogger(__name__)

app_controller = Blueprint("app_controller", __name__)

PAGE_SIZE = 24


@app_controller.get("/")
def dashboard():
    return render_template("pages/home/index.html")


@app_controller.get("/about")
def about():
    return render_template("pages/about/about.html")


@app_controller.get("/explore")
def explore():
    q = request.args.get("q", "").strip()
    page = max(request.args.get("page", 1, type=int), 1)
    objects, total, error = [], 0, False

    try:
        if len(q) >= 2:
            result = skkg_db.search(q, limit=PAGE_SIZE, offset=(page - 1) * PAGE_SIZE)
            objects, total = result["results"], result["total"]
        elif not q:
            objects = skkg_db.get_featured()      # examples before anyone searches
    except Exception:
        logger.exception("Explore search failed")
        error = True

    return render_template(
        "pages/explore/explore.html",
        q=q, objects=objects, total=total, page=page, page_size=PAGE_SIZE, error=error,
    )


@app_controller.get("/explore/<object_id>")
def explore_sub(object_id):
    obj = skkg_db.get_artwork(object_id)
    if not obj:
        abort(404)
    return render_template("pages/explore/explore_sub.html", obj=obj)