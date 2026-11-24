"""
Demo of the whole idea without the website. For one artwork it makes BOTH:
  3D: image -> 3D model (TRELLIS.2) -> amigurumi instructions (Claude)
  2D: image -> colour chart (Pillow)  -> tapestry instructions (Claude)

    python scripts/demo_pipeline.py                     # searches "Hodler"
    python scripts/demo_pipeline.py Medaille --pick 2   # search word, 3rd result
    python scripts/demo_pipeline.py Hodler --skip-3d    # without the slow 3D model
    python scripts/demo_pipeline.py Hodler --width 60 --colors 8   # bigger chart

Needs: app/data/skkg.db (build_skkg_db.py), HF_TOKEN for 3D, ANTHROPIC_API_KEY.
Everything is saved in demo_output/<object id>/.
"""
import argparse
import json
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services import skkg_db
from app.services.chart2d_service import make_chart, save_chart_png
from app.services.crochet_service import generate_instructions, to_markdown
from app.services.model3d_service import create_model, describe_model, model_path
from app.services.skkg_service import get_image_urls

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "demo_output"
STEPS = 7


def step(number: int, text: str) -> float:
    print(f"\n[{number}/{STEPS}] {text}")
    return time.time()


def done(started: float, text: str = "") -> None:
    print(f"      ✓ {text} ({time.time() - started:.1f}s)")


def save_pattern(pattern: dict, out: Path, name: str) -> None:
    (out / f"{name}.json").write_text(json.dumps(pattern, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / f"{name}.md").write_text(to_markdown(pattern), encoding="utf-8")
    if pattern["check"]:
        print("      ! check these steps:", *pattern["check"], sep="\n        ")


def main() -> int:
    parser = argparse.ArgumentParser(description="SKKG crochet demo")
    parser.add_argument("keyword", nargs="?", default="Hodler")
    parser.add_argument("--pick", type=int, default=0, help="which result to use (0 = first with an image)")
    parser.add_argument("--skip-3d", action="store_true", help="skip the 3D model (saves minutes)")
    parser.add_argument("--width", type=int, default=40, help="chart width in stitches")
    parser.add_argument("--colors", type=int, default=6, help="number of yarn colours in the chart")
    args = parser.parse_args()

    # 1. Search ---------------------------------------------------------------
    started = step(1, f"Searching the collection for «{args.keyword}»")
    found = skkg_db.search(args.keyword, limit=10)
    done(started, f"{found['total']} hits, showing {found['count']}")
    for i, artwork in enumerate(found["results"]):
        print(f"      {i:>2}. {artwork['title'][:60]:60} {artwork['artists'][:35]}")
    if not found["results"]:
        print("No artworks found. Try another keyword.")
        return 1

    # 2. Choose an artwork with an image ---------------------------------------
    started = step(2, "Choosing an artwork and loading its image URL")
    candidates = found["results"][args.pick:] + found["results"][:args.pick]
    artwork, image = None, {}
    for candidate in candidates:
        image = get_image_urls(candidate["id"])
        if image.get("image_url"):
            artwork = candidate
            break
        print(f"      (no image for {candidate['id']}, trying the next one)")
    if not artwork:
        print("None of these artworks has an image. Try another keyword.")
        return 1
    done(started, f"«{artwork['title']}» – {artwork['artists']}")
    print(f"      image: {image['image_url']}")

    out = OUTPUT_DIR / artwork["id"]
    out.mkdir(parents=True, exist_ok=True)
    (out / "artwork.json").write_text(
        json.dumps({**artwork, **image}, ensure_ascii=False, indent=2), encoding="utf-8")

    # 3. 3D model -------------------------------------------------------------
    model_info = None
    started = step(3, "3D: generating the model with TRELLIS.2")
    if args.skip_3d:
        print("      skipped (--skip-3d)")
    else:
        try:
            glb = model_path(artwork["id"], "glb")
            if not glb.exists():
                print("      this takes 1–3 minutes, sometimes longer in the queue...")
                glb = create_model(artwork["id"], on_status=lambda m: print(f"      {m}"))
            shutil.copy2(glb, out / "model.glb")
            stl = model_path(artwork["id"], "stl")
            if stl.exists():
                shutil.copy2(stl, out / "model.stl")
            model_info = describe_model(glb)
            done(started, f"model saved, proportions {model_info['proportions_width_height_depth']}")
        except Exception as exc:
            print(f"      ✗ 3D failed: {exc}")
            print("      continuing – the amigurumi is then based on the image only")

    # 4. 2D chart -------------------------------------------------------------
    chart = None
    started = step(4, f"2D: making the colour chart ({args.width} stitches wide, {args.colors} colours)")
    try:
        chart = make_chart(image["image_url"], width=args.width, colors=args.colors)
        save_chart_png(chart, out / "chart.png")
        (out / "chart.json").write_text(json.dumps(chart), encoding="utf-8")
        colours = ", ".join(f"{c['letter']} {c['hex']}" for c in chart["colors"])
        done(started, f"{chart['width']} × {chart['height']} stitches, colours: {colours}")
    except Exception as exc:
        print(f"      ✗ Chart failed: {exc}")

    # 5. Amigurumi instructions (3D) ------------------------------------------
    results = {}
    started = step(5, "3D: writing amigurumi instructions with Claude")
    try:
        pattern = generate_instructions(artwork, image["image_url"], "amigurumi", model_info=model_info)
        save_pattern(pattern, out, "instructions_3d")
        results["3D amigurumi"] = pattern
        done(started, f"«{pattern.get('title')}», {len(pattern.get('parts', []))} parts")
    except Exception as exc:
        print(f"      ✗ Amigurumi instructions failed: {exc}")

    # 6. Tapestry instructions (2D) -------------------------------------------
    started = step(6, "2D: writing tapestry instructions with Claude")
    if not chart:
        print("      skipped (no chart)")
    else:
        try:
            pattern = generate_instructions(artwork, image["image_url"], "tapestry", chart=chart)
            save_pattern(pattern, out, "instructions_2d")
            results["2D tapestry"] = pattern
            done(started, f"«{pattern.get('title')}», {len(pattern['chart_rows'])} chart rows")
        except Exception as exc:
            print(f"      ✗ Tapestry instructions failed: {exc}")

    # 7. Result ---------------------------------------------------------------
    step(7, "Result")
    for name, pattern in results.items():
        materials = pattern.get("materials", {})
        print(f"\n   {name}: «{pattern.get('title')}»")
        print(f"      difficulty {pattern.get('difficulty')}, size {pattern.get('finished_size_cm')} cm, "
              f"hook {materials.get('hook_mm')} mm, {len(materials.get('yarn', []))} yarn colours")
    print(f"\nAll files saved in: {out}")
    for file in sorted(out.iterdir()):
        print(f"   {file.name}")
    print("\nOpen instructions_3d.md / instructions_2d.md to read the patterns, "
          "chart.png for the chart, model.glb for the 3D model.")
    return 0 if results else 1


if __name__ == "__main__":
    sys.exit(main())