"""
Artwork image -> 3D model (GLB, plus STL) via the microsoft/TRELLIS.2
Hugging Face Space. Based on scripts image_to_glb.py and glb_to_stl.py.

One generation takes minutes, so it runs as a background job:
    start_job(object_id)  -> returns immediately with a job_id
    get_job(job_id)       -> "queued" | "running" | "done" | "failed"
Finished models are saved in app/data/models/<object_id>.glb/.stl and reused.

Requires:  pip install gradio_client trimesh
           HF_TOKEN environment variable (Hugging Face token)
"""
import logging
import os
import shutil
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from app.services.skkg_service import get_image_urls

logger = logging.getLogger(__name__)

SPACE_ID = "microsoft/TRELLIS.2"
MODELS_DIR = Path(__file__).resolve().parent.parent / "data" / "models"

# Smaller settings than the CLI defaults: faster, less GPU quota, lighter for the browser
RESOLUTION = "512"
FACES = 100_000
TEXTURE_SIZE = 1024
MAX_RETRIES = 2

# Substrings that suggest a temporary quota/queue problem worth retrying.
RETRYABLE = ("quota", "queue", "busy", "capacity", "too many", "rate limit", "exceeded")

_executor = ThreadPoolExecutor(max_workers=1)   # one generation at a time (GPU quota)
_jobs: dict = {}                                 # job_id -> job dict (lost on restart)
_jobs_lock = threading.Lock()


# ---------------------------------------------------------------- files

def model_path(object_id: str, ext: str) -> Path:
    return MODELS_DIR / f"{object_id}.{ext}"


def model_exists(object_id: str) -> bool:
    return model_path(object_id, "glb").exists()


# ---------------------------------------------------------------- TRELLIS.2 (from image_to_glb.py)

def _connect(token):
    from gradio_client import Client
    if not token:
        return Client(SPACE_ID)
    try:
        return Client(SPACE_ID, token=token)
    except TypeError:
        return Client(SPACE_ID, hf_token=token)


def _as_path(result):
    """Pull a local file path out of whatever shape gradio_client returns."""
    if result is None:
        return None
    if isinstance(result, str):
        return result if os.path.exists(result) else None
    if isinstance(result, dict):
        for key in ("path", "value", "name"):
            if key in result:
                found = _as_path(result[key])
                if found:
                    return found
        return None
    if isinstance(result, (tuple, list)):
        for item in result:
            found = _as_path(item)
            if found:
                return found
    return None


def _find_glb(result):
    items = result if isinstance(result, (tuple, list)) else [result]
    for item in items:
        path = _as_path(item)
        if path and path.lower().endswith(".glb"):
            return path
    return _as_path(result)


def _generate_glb(client, image_url: str) -> str:
    """Runs the Space's steps in order on ONE client (the Space keeps session state)."""
    from gradio_client import handle_file

    try:
        client.predict(api_name="/start_session")
    except Exception as exc:  # not fatal on every Space version
        logger.info("start_session skipped: %s", exc)

    pre = client.predict(handle_file(image_url), api_name="/preprocess_image")
    processed = _as_path(pre) or image_url

    seed = client.predict(True, 0, api_name="/get_seed")
    client.predict(
        handle_file(processed), seed, RESOLUTION,
        7.5, 0.7, 12, 5.0,    # sparse structure
        7.5, 0.5, 12, 3.0,    # shape latent
        1.0, 0.0, 12, 3.0,    # texture latent
        api_name="/image_to_3d",
    )
    glb = client.predict(FACES, TEXTURE_SIZE, api_name="/extract_glb")
    path = _find_glb(glb)
    if not path:
        raise RuntimeError(f"No GLB file in the Space's response: {glb!r}")
    return path


def _convert_to_stl(glb_path: Path, stl_path: Path) -> None:
    """From glb_to_stl.py. force='mesh' merges a GLB scene into one mesh for STL."""
    import trimesh
    trimesh.load(glb_path, force="mesh").export(stl_path)


# ---------------------------------------------------------------- jobs

def _update(job_id: str, **changes) -> None:
    with _jobs_lock:
        _jobs[job_id].update(changes)


def create_model(object_id: str, on_status=lambda message: None) -> Path:
    """
    Generate the GLB (+ STL) for one artwork and return the GLB path.
    Runs synchronously (minutes!). Used by the job system and by the demo script.
    """
    image_url = get_image_urls(object_id).get("image_url")
    if not image_url:
        raise ValueError("This artwork has no image.")

    token = os.environ.get("HF_TOKEN")
    for attempt in range(MAX_RETRIES + 1):
        try:
            generated = _generate_glb(_connect(token), image_url)
            break
        except Exception as exc:
            retryable = any(word in str(exc).lower() for word in RETRYABLE)
            if attempt < MAX_RETRIES and retryable:
                wait = 30 * (attempt + 1)
                logger.warning("TRELLIS busy (%s), retrying in %ss", exc, wait)
                on_status(f"Service busy, retrying in {wait}s...")
                time.sleep(wait)
                continue
            raise

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    glb_path = model_path(object_id, "glb")
    tmp_path = glb_path.with_suffix(".glb.tmp")
    shutil.copy2(generated, tmp_path)
    os.replace(tmp_path, glb_path)          # file only appears once complete

    try:
        _convert_to_stl(glb_path, model_path(object_id, "stl"))
    except Exception:
        logger.exception("STL conversion failed for %s (GLB is still fine)", object_id)

    return glb_path


def describe_model(glb_path: Path) -> dict:
    """Rough shape info for the crochet instructions: proportions of the model."""
    import trimesh
    mesh = trimesh.load(glb_path, force="mesh")
    width, height, depth = (float(x) for x in mesh.extents)
    biggest = max(width, height, depth) or 1.0
    return {
        "proportions_width_height_depth": [round(width / biggest, 2),
                                           round(height / biggest, 2),
                                           round(depth / biggest, 2)],
        "faces": int(len(mesh.faces)),
    }


def _run_job(job_id: str, object_id: str) -> None:
    _update(job_id, status="running", message="Generating 3D model (this takes a few minutes)...")
    try:
        create_model(object_id, on_status=lambda message: _update(job_id, message=message))
        _update(job_id, status="done", message="Done.")
    except ValueError as exc:
        _update(job_id, status="failed", message=str(exc))
    except Exception:
        logger.exception("3D generation failed for %s", object_id)
        _update(job_id, status="failed", message="3D generation failed. Please try again later.")


def start_job(object_id: str) -> dict:
    """Start a generation, or reuse a finished model / a job already running."""
    if model_exists(object_id):
        return {"job_id": None, "object_id": object_id, "status": "done", "message": "Already generated."}

    with _jobs_lock:
        for job in _jobs.values():
            if job["object_id"] == object_id and job["status"] in ("queued", "running"):
                return dict(job)

        job_id = uuid.uuid4().hex
        _jobs[job_id] = {
            "job_id": job_id,
            "object_id": object_id,
            "status": "queued",
            "message": "Waiting for a free slot...",
        }
        job = dict(_jobs[job_id])

    _executor.submit(_run_job, job_id, object_id)
    return job


def get_job(job_id: str):
    with _jobs_lock:
        job = _jobs.get(job_id)
        return dict(job) if job else None