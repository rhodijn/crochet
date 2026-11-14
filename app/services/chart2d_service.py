"""
Artwork image -> 2D crochet colour chart (tapestry crochet).

Every cell of the grid is one stitch. The image is shrunk to the chart size
and reduced to a few yarn colours. Pure Python (Pillow), no AI involved,
so the chart is always exact.

Requires:  pip install pillow
"""
import io
import string

import requests
from PIL import Image, ImageDraw

CELL_PX = 14              # size of one stitch in chart.png
MIN_COLOR_DISTANCE = 30   # colours closer than this are merged (RGB distance)
LETTERS = string.ascii_uppercase


def _distance(a: tuple, b: tuple) -> float:
    return sum((x - y) ** 2 for x, y in zip(a, b)) ** 0.5


def _load_image(image_url: str) -> Image.Image:
    response = requests.get(image_url, timeout=60)
    response.raise_for_status()
    return Image.open(io.BytesIO(response.content)).convert("RGB")


def make_chart(image_url: str, width: int = 40, colors: int = 6) -> dict:
    """
    Returns:
      {
        "width": 40, "height": 52,
        "colors": [{"letter": "A", "hex": "#5a4a3a", "stitches": 512}, ...],
        "grid":   [[0, 0, 1, ...], ...]   # top row first, values index into "colors"
      }
    """
    image = _load_image(image_url)
    height = max(1, round(width * image.height / image.width))
    small = image.resize((width, height), Image.LANCZOS)
    # FASTOCTREE keeps small but distinct colours (faces, details); MEDIANCUT
    # spends most colours on shades of the large background.
    quantized = small.quantize(colors=colors, method=Image.Quantize.FASTOCTREE)

    palette = quantized.getpalette()
    get_pixels = getattr(quantized, "get_flattened_data", quantized.getdata)
    pixels = list(get_pixels())
    rgb = {i: tuple(palette[i * 3: i * 3 + 3]) for i in set(pixels)}

    counts = {}
    for p in pixels:
        counts[p] = counts.get(p, 0) + 1

    # Merge colours that are nearly identical into the more frequent one.
    used = sorted(counts, key=counts.get, reverse=True)
    target = {}
    kept = []
    for c in used:
        close = next((k for k in kept if _distance(rgb[c], rgb[k]) < MIN_COLOR_DISTANCE), None)
        if close is None:
            kept.append(c)
            target[c] = c
        else:
            target[c] = close
            counts[close] += counts[c]
    pixels = [target[p] for p in pixels]

    # Most frequent first -> A, B, C ...
    kept.sort(key=counts.get, reverse=True)
    new_index = {old: new for new, old in enumerate(kept)}
    color_list = [
        {"letter": LETTERS[i], "hex": "#%02x%02x%02x" % rgb[old], "stitches": counts[old]}
        for i, old in enumerate(kept)
    ]

    grid = [
        [new_index[pixels[y * width + x]] for x in range(width)]
        for y in range(height)
    ]
    return {"width": width, "height": height, "colors": color_list, "grid": grid}


def row_instructions(chart: dict) -> list:
    """
    Row-by-row colour runs in working order.
    Row 1 is the BOTTOM row of the picture. Odd rows are worked right to left,
    even rows left to right (you turn the work after every row).
    """
    letters = [c["letter"] for c in chart["colors"]]
    rows = []
    for number, cells in enumerate(reversed(chart["grid"]), start=1):
        direction = "right to left" if number % 2 == 1 else "left to right"
        ordered = list(reversed(cells)) if number % 2 == 1 else cells
        runs, current, count = [], ordered[0], 0
        for cell in ordered:
            if cell == current:
                count += 1
            else:
                runs.append(f"{count} {letters[current]}")
                current, count = cell, 1
        runs.append(f"{count} {letters[current]}")
        rows.append({"row": number, "direction": direction,
                     "runs": ", ".join(runs), "stitch_count": len(cells)})
    return rows


def save_chart_png(chart: dict, path) -> None:
    """Draw the chart: one square per stitch, a darker line every 10 stitches."""
    w, h = chart["width"], chart["height"]
    margin = 30
    img = Image.new("RGB", (w * CELL_PX + margin, h * CELL_PX + margin), "white")
    draw = ImageDraw.Draw(img)
    hexes = [c["hex"] for c in chart["colors"]]

    for y, row in enumerate(chart["grid"]):
        for x, cell in enumerate(row):
            x0, y0 = x * CELL_PX, y * CELL_PX
            draw.rectangle([x0, y0, x0 + CELL_PX, y0 + CELL_PX], fill=hexes[cell])

    for x in range(w + 1):
        draw.line([(x * CELL_PX, 0), (x * CELL_PX, h * CELL_PX)],
                  fill="#333333" if x % 10 == 0 else "#bbbbbb")
    for y in range(h + 1):
        draw.line([(0, y * CELL_PX), (w * CELL_PX, y * CELL_PX)],
                  fill="#333333" if (h - y) % 10 == 0 else "#bbbbbb")

    # row numbers on the right (row 1 = bottom), every 5 rows
    for row in range(1, h + 1):
        if row == 1 or row % 5 == 0:
            y = (h - row) * CELL_PX + 2
            draw.text((w * CELL_PX + 4, y), str(row), fill="black")
    img.save(path)