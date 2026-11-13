#!/usr/bin/env python3
"""
Convert a single image to a GLB 3D model using the microsoft/TRELLIS.2
Hugging Face Space via gradio_client.

REQUIRES A HUGGING FACE TOKEN via environment variable HF_TOKEN:
    export HF_TOKEN=hf_xxx

Usage:
    python image_to_glb.py input.png         # works with an image URL as well
    python image_to_glb.py input.png -o model.glb --resolution 512
    python image_to_glb.py --show-api        # print the Space's current endpoints
"""

import argparse
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import urlopen

from gradio_client import Client, handle_file

SPACE_ID = "microsoft/TRELLIS.2"

# Substrings that suggest a temporary quota/queue problem worth retrying.
RETRYABLE = ("quota", "queue", "busy", "capacity", "too many", "rate limit", "exceeded")


def is_http_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def resolve_image_source(image_input: str) -> tuple[Path, str | None]:
    """
    Resolve image input to a local Path.

    Returns (image_path, temp_file_path). temp_file_path is set only for URL inputs
    and should be deleted by the caller.
    """
    if not is_http_url(image_input):
        image_path = Path(image_input)
        if not image_path.is_file():
            raise ValueError("please provide a valid input image path")
        return image_path, None

    parsed = urlparse(image_input)
    suffix = Path(parsed.path).suffix or ".img"

    with urlopen(image_input, timeout=60) as response:
        status = getattr(response, "status", 200)
        if status and status >= 400:
            raise ValueError(f"failed to download image URL (HTTP {status})")
        content = response.read()

    if not content:
        raise ValueError("downloaded image is empty")

    with tempfile.NamedTemporaryFile(prefix="img_to_glb_", suffix=suffix, delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    return Path(tmp_path), tmp_path


def connect(token: str | None) -> Client:
    """Create a client. Newer gradio_client uses `token`, older uses `hf_token`."""
    if not token:
        return Client(SPACE_ID)
    try:
        return Client(SPACE_ID, token=token)
    except TypeError:
        return Client(SPACE_ID, hf_token=token)


def as_path(result) -> str | None:
    """Pull a local file path out of whatever shape gradio_client returns."""
    if result is None:
        return None
    if isinstance(result, str):
        return result if os.path.exists(result) else None
    if isinstance(result, dict):
        # e.g. {"path": "...", "url": ...} or {"value": {...}}
        for key in ("path", "value", "name"):
            if key in result:
                found = as_path(result[key])
                if found:
                    return found
        return None
    if isinstance(result, (tuple, list)):
        for item in result:
            found = as_path(item)
            if found:
                return found
    return None


def find_glb(result) -> str | None:
    """Like as_path, but prefer a path that actually ends in .glb."""
    items = result if isinstance(result, (tuple, list)) else [result]
    for item in items:
        p = as_path(item)
        if p and p.lower().endswith(".glb"):
            return p
    return as_path(result)


def generate(
    image: Path,
    client: Client,
    seed: int,
    randomize_seed: bool,
    resolution: str,
    decimation_target: int,
    texture_size: int,
) -> str:
    # The Space keeps per-session state server-side, so every step below must
    # use the SAME client object, in this order.

    print("[1/5] Starting session...")
    try:
        client.predict(api_name="/start_session")
    except Exception as e:  # not fatal on every Space version
        print(f"      (start_session skipped: {e})")

    print("[2/5] Preprocessing image (background removal / crop)...")
    pre = client.predict(handle_file(str(image)), api_name="/preprocess_image")
    processed = as_path(pre) or str(image)

    print("[3/5] Resolving seed...")
    actual_seed = client.predict(randomize_seed, seed, api_name="/get_seed")
    print(f"      seed = {actual_seed}")

    print(f"[4/5] Generating 3D at {resolution} (can take 1-3 min)...")
    client.predict(
        handle_file(processed),
        actual_seed,
        resolution,
        # sparse structure: guidance strength, rescale, steps, rescale_t
        7.5, 0.7, 12, 5.0,
        # shape latent
        7.5, 0.5, 12, 3.0,
        # texture latent
        1.0, 0.0, 12, 3.0,
        api_name="/image_to_3d",
    )

    print("[5/5] Extracting GLB...")
    glb = client.predict(decimation_target, texture_size, api_name="/extract_glb")
    path = find_glb(glb)
    if not path:
        raise RuntimeError(f"Could not find a GLB file in the response: {glb!r}")
    return path


def main() -> int:
    ap = argparse.ArgumentParser(description="Image -> GLB via TRELLIS.2 HF Space")
    ap.add_argument("image", nargs="?", help="input image path or HTTP/HTTPS URL")
    ap.add_argument("-o", "--output", type=Path, help="output .glb (default: <image>.glb)")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--fixed-seed", action="store_true", help="use --seed as-is instead of randomizing")
    ap.add_argument("--resolution", choices=["512", "1024", "1536"], default="1024",
                    help="lower = faster and uses less GPU quota")
    ap.add_argument("--faces", type=int, default=300_000, help="mesh decimation target (face count)")
    ap.add_argument("--texture-size", type=int, default=2048)
    ap.add_argument("--retries", type=int, default=4, help="retries on quota/queue errors")
    ap.add_argument("--show-api", action="store_true", help="print the Space's endpoints and exit")
    args = ap.parse_args()

    token = os.environ.get("HF_TOKEN")
    print(f"Connecting to {SPACE_ID} {'with' if token else 'without'} HF token...")
    client = connect(token)

    if args.show_api:
        client.view_api()
        return 0

    if not args.image:
        ap.error("please provide an input image path or URL")

    temp_image_path: str | None = None
    try:
        image_path, temp_image_path = resolve_image_source(args.image)
    except Exception as e:
        ap.error(str(e))

    output = args.output or image_path.with_suffix(".glb")

    try:
        for attempt in range(args.retries + 1):
            try:
                glb_path = generate(
                    image_path, client, args.seed, not args.fixed_seed,
                    args.resolution, args.faces, args.texture_size,
                )
                break
            except Exception as e:
                msg = str(e).lower()
                if attempt < args.retries and any(k in msg for k in RETRYABLE):
                    wait = min(30 * (attempt + 1), 120)
                    print(f"Quota/queue problem ({e}). Retrying in {wait}s "
                          f"[{attempt + 1}/{args.retries}]...")
                    time.sleep(wait)
                    client = connect(token)  # fresh session for the retry
                    continue
                print(f"Failed: {e}", file=sys.stderr)
                return 1

        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(glb_path, output)
        size_mb = output.stat().st_size / (1024 * 1024)
        print(f"Saved {output} ({size_mb:.1f} MB)")
        return 0
    finally:
        if temp_image_path and os.path.exists(temp_image_path):
            os.remove(temp_image_path)


if __name__ == "__main__":
    sys.exit(main())