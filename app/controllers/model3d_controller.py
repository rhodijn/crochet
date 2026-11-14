import re

from flask import Blueprint, jsonify, request, send_file

from app.services.model3d_service import get_job, model_path, start_job

model3d_controller = Blueprint("model3d_controller", __name__, url_prefix="/api/model3d")

OBJECT_ID = re.compile(r"[A-Za-z0-9-]{1,64}")


def error(message: str, status: int):
    return jsonify({"success": False, "message": message}), status


def with_urls(job: dict) -> dict:
    """Add the download URLs once the model is ready."""
    if job["status"] == "done":
        object_id = job["object_id"]
        job["glb_url"] = f"/api/model3d/files/{object_id}.glb"
        if model_path(object_id, "stl").exists():
            job["stl_url"] = f"/api/model3d/files/{object_id}.stl"
    return {"success": job["status"] != "failed", **job}


@model3d_controller.post("/generate")
def generate_model():
    object_id = str((request.get_json(silent=True) or {}).get("object_id", "")).strip()
    if not OBJECT_ID.fullmatch(object_id):
        return error("Please send a valid object_id.", 400)

    job = start_job(object_id)
    status = 200 if job["status"] == "done" else 202   # 202 = accepted, still working
    return jsonify(with_urls(job)), status


@model3d_controller.get("/jobs/<job_id>")
def job_status(job_id: str):
    job = get_job(job_id)
    if not job:
        return error("Unknown job (the server may have restarted). Start it again.", 404)
    return jsonify(with_urls(job))


@model3d_controller.get("/files/<object_id>.<ext>")
def model_file(object_id: str, ext: str):
    if not OBJECT_ID.fullmatch(object_id) or ext not in ("glb", "stl"):
        return error("Invalid file.", 400)
    path = model_path(object_id, ext)
    if not path.exists():
        return error("Model not found.", 404)
    if ext == "glb":
        return send_file(path, mimetype="model/gltf-binary")
    return send_file(path, mimetype="model/stl", as_attachment=True,
                     download_name=f"skkg-{object_id}.stl")