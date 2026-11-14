"""
Crochet instructions for an artwork, written by Claude from the artwork image.
Two kinds, made for every artwork:
  - "amigurumi": 3D figure, uses the proportions of the 3D model if available
  - "tapestry":  2D picture, built on the colour chart from chart2d_service

Requires:  pip install anthropic
           ANTHROPIC_API_KEY in app/config/settings.py (Settings) or as environment variable
"""
import json
import os
import re

CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-5-5")


def get_api_key():
    """The Anthropic key from Settings, falling back to the environment variable."""
    try:
        from app.config.settings import Settings
        key = getattr(Settings(), "ANTHROPIC_API_KEY", None)
    except Exception:
        key = None
    return key or os.getenv("ANTHROPIC_API_KEY")
MAX_TOKENS = 16000   # long amigurumi patterns need room; JSON cut off = invalid

# Standard yarn weights (Craft Yarn Council). Gauge = single crochet per 10 cm,
# approximate; real gauge depends on the yarn and on how tightly someone crochets.
YARN_WEIGHTS = {
    "fine":   {"label": "Fine (sport, CYC 2)",          "hook_mm": 3.0, "sc_per_10cm": 22, "rows_per_10cm": 24, "amigurumi_hook_mm": 2.5},
    "light":  {"label": "Light (DK, CYC 3)",            "hook_mm": 4.0, "sc_per_10cm": 18, "rows_per_10cm": 20, "amigurumi_hook_mm": 3.0},
    "medium": {"label": "Medium (worsted/aran, CYC 4)", "hook_mm": 5.0, "sc_per_10cm": 15, "rows_per_10cm": 17, "amigurumi_hook_mm": 3.5},
    "bulky":  {"label": "Bulky (chunky, CYC 5)",        "hook_mm": 6.5, "sc_per_10cm": 11, "rows_per_10cm": 13, "amigurumi_hook_mm": 5.0},
}
DEFAULT_YARN = "light"


def finished_size_cm(width_stitches: int, height_rows: int, yarn_weight: str) -> tuple:
    """Approximate size of a single crochet piece in this yarn weight."""
    yarn = YARN_WEIGHTS[yarn_weight]
    return (round(width_stitches / yarn["sc_per_10cm"] * 10),
            round(height_rows / yarn["rows_per_10cm"] * 10))


SYSTEM_PROMPT = """You are an experienced crochet designer. You turn artworks from a
museum collection into crochet patterns that a hobby crocheter can actually follow.

Rules:
- Use US crochet terminology only, never UK terms (US sc = UK dc).
- Use only standard US crochet abbreviations: ch, sl st, sc, hdc, dc, tr, inc, dec,
  sc2tog, st(s), rnd(s), rep, sk, sp, FLO, BLO, pop, MR (magic ring), RS, WS.
  Do not invent abbreviations. List every abbreviation you use, and only those, in
  "abbreviations".
- Write the kind of pattern the request asks for (amigurumi or tapestry).
- Use the yarn weight and hook size given in the request. Do not switch to another yarn.
- Use exactly the number of yarn colours the request allows, not more.
- Every round/row must state its stitch count, and the counts must add up.
- Keep it achievable: about 2 to 6 parts. Simplify small details (straps, buttons,
  small accessories) into one or two short steps instead of separate parts.
- Keep the whole answer compact: combine identical rounds ("Rnd 8-12: sc around (36)").
- In "yarn_note" write one or two sentences: which yarn weight and hook the finished
  size is based on, and that a thinner or thicker yarn makes the piece smaller or larger,
  so the crocheter should check their gauge first.

Answer with JSON only, no other text, in exactly this shape:
{
  "title": "pattern name",
  "pattern_type": "amigurumi" or "tapestry",
  "difficulty": "beginner" | "intermediate" | "advanced",
  "finished_size_cm": "e.g. 15 x 10 x 8",
  "yarn_note": "Made with light (DK) yarn and a 4.0 mm hook ...",
  "materials": {
    "yarn": [{"color": "name", "hex": "#rrggbb", "amount_g": 20}],
    "hook_mm": 3.0,
    "other": ["stuffing", "safety eyes"]
  },
  "abbreviations": {"sc": "single crochet"},
  "parts": [
    {"name": "Body", "color": "name",
     "steps": [{"step": "Rnd 1", "instruction": "6 sc in MR", "stitch_count": 6}],
     "preview": "only for amigurumi parts in rounds, see the task"}
  ],
  "assembly": ["how to put the parts together"],
  "notes": "short tips"
}"""


AMIGURUMI_TASK = (
    "Write an AMIGURUMI pattern (a 3D crocheted figure, worked in rounds) of the "
    "main subject of this artwork. If the artwork is flat (a painting or drawing), "
    "turn its main figure or object into a 3D figure. "
    "Shape every part like the real thing instead of plain tubes and balls: change the "
    "stitch count in the middle rounds (inc to widen, dec to narrow) so parts taper, bulge "
    "or flatten where the object does, and follow the proportions of the 3D model. "
    "A part should only stay at the same count for many rounds if the object is really "
    "straight there."
)

# Notation for the 3D crochet preview (read by static/javascripts/crochet-viewer.js).
PREVIEW_RULES = """
In EVERY part worked in rounds, also add a "preview" field: that part's rounds in
CrochetPARADE notation (read by static/javascripts/crochet-viewer.js), one line per
round, worked in a continuous spiral. It must match the part's rounds exactly.
Start it with a COLOR line for the part's yarn. For flat parts worked in rows from a
chain, set "preview" to "".
  ring            magic ring (always the first line)
  6 sc            6 sc (on line 2: 6 sc into the ring)
  6 inc           6 increases (each inc = 2 sc in one stitch)
  6 dec           6 decreases (each dec = sc2tog)
  6*(sc,inc)      repeat the group 6 times; 6*(2 sc,inc) = 2 sc then inc, 6 times
  COLOR: red      colour for the following rounds, as a plain colour NAME (red, navy,
                  beige, ...). Never use "#" – it starts a comment in CrochetPARADE.
Only use: ring, sc, inc, dec, N*(...) repeats, COLOR lines. No text, no stitch counts,
no round labels, no comments. "preview" must be ONE string with the rounds separated
by line breaks (\\n), not a list. Example:
COLOR: red
ring
6 sc
6 inc
6*(sc,inc)
18 sc
18 sc
6*(sc,dec)
6 dec"""

TAPESTRY_TASK = (
    "Write a TAPESTRY CROCHET pattern (a flat picture in sc, worked in rows). "
    "The colour chart is already computed and its row-by-row colour runs will be printed "
    "after your text, so do NOT write the picture rows yourself. Use exactly the chart's "
    "colours as the yarn list (keep the letters A, B, C ... and their hex values, give each "
    "a yarn colour name, estimate grams from the stitch counts and the yarn weight). "
    "In 'parts' describe only the work around the chart: foundation ch, how to read the "
    "chart, how to change colours and carry yarn, and a simple sc border."
)


def _yarn_text(kind: str, yarn_weight: str, colors: int, chart: dict = None) -> list:
    yarn = YARN_WEIGHTS[yarn_weight]
    if kind == "amigurumi":
        return [
            f"Yarn chosen by the user: {yarn['label']}. Use a {yarn['amigurumi_hook_mm']} mm hook "
            "(smaller than the yarn label suggests, so the fabric is tight and the stuffing "
            "does not show). Mention this in yarn_note.",
            f"Use at most {colors} yarn colours.",
        ]
    width_cm, height_cm = finished_size_cm(chart["width"], chart["height"], yarn_weight)
    return [
        f"Yarn chosen by the user: {yarn['label']}, hook {yarn['hook_mm']} mm, "
        f"gauge about {yarn['sc_per_10cm']} sc and {yarn['rows_per_10cm']} rows = 10 cm.",
        f"With this gauge the chart area is about {width_cm} x {height_cm} cm. Use this "
        "(plus the border) for finished_size_cm and explain it in yarn_note.",
        f"The user chose {len(chart['colors'])} colours; the chart uses exactly these.",
    ]


def _artwork_text(artwork: dict, kind: str, model_info: dict = None, chart: dict = None,
                  yarn_weight: str = DEFAULT_YARN, colors: int = 6) -> str:
    lines = [
        AMIGURUMI_TASK + PREVIEW_RULES if kind == "amigurumi" else TAPESTRY_TASK,
        "The artwork is from the SKKG collection.",
        f"Title: {artwork.get('title') or 'unknown'}",
        f"Artist: {artwork.get('artists') or 'unknown'}",
        f"Date: {artwork.get('date') or 'unknown'}",
        f"Gattung (type): {artwork.get('gattung') or 'unknown'}",
        f"Material/technique: {artwork.get('material') or 'unknown'}",
        *_yarn_text(kind, yarn_weight, colors, chart),
    ]
    if kind == "amigurumi" and model_info:
        lines.append(
            "A 3D model was generated from the image. Its proportions "
            f"(width, height, depth, largest = 1): {model_info['proportions_width_height_depth']}. "
            "Use them for the shape of the amigurumi."
        )
    if kind == "tapestry" and chart:
        colours = ", ".join(f"{c['letter']} {c['hex']} ({c['stitches']} stitches)"
                            for c in chart["colors"])
        lines.append(
            f"Chart: {chart['width']} stitches wide, {chart['height']} rows high. "
            f"Colours: {colours}."
        )
    return "\n".join(lines)


# CSS colour names (CrochetPARADE uses names because "#" starts a comment).
_COLOR_NAMES = {
    "black": (0, 0, 0), "dimgray": (105, 105, 105), "gray": (128, 128, 128), "darkgray": (169, 169, 169),
    "silver": (192, 192, 192), "lightgray": (211, 211, 211), "white": (255, 255, 255), "ivory": (255, 255, 240),
    "beige": (245, 245, 220), "wheat": (245, 222, 179), "tan": (210, 180, 140), "burlywood": (222, 184, 135),
    "peru": (205, 133, 63), "chocolate": (210, 105, 30), "sienna": (160, 82, 45), "saddlebrown": (139, 69, 19),
    "brown": (165, 42, 42), "maroon": (128, 0, 0), "darkred": (139, 0, 0), "firebrick": (178, 34, 34),
    "red": (255, 0, 0), "crimson": (220, 20, 60), "indianred": (205, 92, 92), "salmon": (250, 128, 114),
    "coral": (255, 127, 80), "tomato": (255, 99, 71), "orangered": (255, 69, 0), "darkorange": (255, 140, 0),
    "orange": (255, 165, 0), "goldenrod": (218, 165, 32), "gold": (255, 215, 0), "khaki": (240, 230, 140),
    "yellow": (255, 255, 0), "olive": (128, 128, 0), "olivedrab": (107, 142, 35), "yellowgreen": (154, 205, 50),
    "darkolivegreen": (85, 107, 47), "green": (0, 128, 0), "darkgreen": (0, 100, 0), "forestgreen": (34, 139, 34),
    "seagreen": (46, 139, 87), "mediumseagreen": (60, 179, 113), "lightgreen": (144, 238, 144), "teal": (0, 128, 128),
    "darkcyan": (0, 139, 139), "cadetblue": (95, 158, 160), "turquoise": (64, 224, 208), "lightblue": (173, 216, 230),
    "skyblue": (135, 206, 235), "steelblue": (70, 130, 180), "cornflowerblue": (100, 149, 237), "royalblue": (65, 105, 225),
    "blue": (0, 0, 255), "mediumblue": (0, 0, 205), "darkblue": (0, 0, 139), "navy": (0, 0, 128),
    "midnightblue": (25, 25, 112), "slategray": (112, 128, 144), "darkslategray": (47, 79, 79), "lavender": (230, 230, 250),
    "thistle": (216, 191, 216), "plum": (221, 160, 221), "orchid": (218, 112, 214), "purple": (128, 0, 128),
    "indigo": (75, 0, 130), "pink": (255, 192, 203), "hotpink": (255, 105, 180), "palevioletred": (219, 112, 147),
}


def _nearest_color_name(r: int, g: int, b: int) -> str:
    return min(_COLOR_NAMES, key=lambda n: sum((x - y) ** 2 for x, y in zip(_COLOR_NAMES[n], (r, g, b))))


_PREVIEW_WORD = re.compile(r"^(ring|sc|inc|dec|ch|sc2tog|sc\d+inc)$")


def normalize_preview(preview):
    """
    Clean Claude's preview into the exact notation crochet-viewer.js reads,
    or return None if it cannot be used. Fixes common variations: a list instead
    of one text, "Rnd 3:" labels, "(18)" stitch counts, "x6" repeats, "MR", capitals.
    """
    if not preview:
        return None
    lines = preview if isinstance(preview, list) else str(preview).replace("\\n", "\n").splitlines()
    out = []
    for raw in lines:
        line = str(raw).strip()
        color = re.match(r"(?i)^colou?r\s*:\s*(.+?)\s*$", line)
        if color:
            value = color.group(1).lower().replace(" ", "")
            hexm = re.fullmatch(r"#?([0-9a-f]{6})", value)
            rgbm = re.fullmatch(r"rgb\((\d{1,3}),(\d{1,3}),(\d{1,3})\)", value)
            if value in _COLOR_NAMES:
                out.append(f"COLOR: {value}")
            elif hexm:
                h = hexm.group(1)
                out.append(f"COLOR: {_nearest_color_name(int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))}")
            elif rgbm:
                out.append(f"COLOR: {_nearest_color_name(*(int(x) for x in rgbm.groups()))}")
            continue                                  # unknown colour: leave it out
        line = line.split("#")[0]                                            # comments
        line = re.sub(r"(?i)^\s*(rnds?|rounds?|rows?|r)\s*[\d\-–]+\s*[:.)\-]\s*", "", line)  # "Rnd 3:"
        line = re.sub(r"[\(\[]\s*\d+\s*(sts?|stitches)?\s*[\)\]]\s*$", "", line)          # "(18)"
        line = line.lower()
        line = re.sub(r"\b(magic ring|mr)\b", "ring", line)
        line = re.sub(r"^(\d+)\s*sc\s+(in|into)\s+(the\s+)?ring$", r"sc\1inc", line.strip())  # "6 sc in ring"
        line = re.sub(r"\b(inc|dec|sc)\s*x\s*(\d+)\b", r"\2\1", line)                     # "inc x6"
        line = re.sub(r"(\([^()]*\))\s*[x×]\s*(\d+)", r"\1*\2", line)                       # "(..) x6"
        line = re.sub(r"\s+", " ", line).strip(" ,")
        if line:
            out.append(line)

    # CrochetPARADE style, like the team's sample: "6 sc", "6 inc", "6*(sc,inc)"
    styled = []
    for line in out:
        if not line.startswith("COLOR:"):
            line = re.sub(r"^sc(\d+)inc$", r"\1 sc", line)                 # 6 sc into the ring
            line = re.sub(r"(\([^()]*\))\s*\*\s*(\d+)", r"\2*\1", line)   # (..)*6 -> 6*(..)
            line = re.sub(r"\b(\d+)\s*(sc|inc|dec)\b", r"\1 \2", line)    # 6inc -> 6 inc
            line = re.sub(r"\s*,\s*", ",", line)
        styled.append(line)
    out = styled

    rounds = [l for l in out if not l.startswith("COLOR:")]
    if len(rounds) < 2:
        return None
    for line in rounds:
        if re.search(r"[^a-z0-9(),*\s]", line):
            return None
        if not all(_PREVIEW_WORD.match(w) for w in re.findall(r"[a-z_]\w*", line)):
            return None
    return "\n".join(out)


def apply_previews(pattern: dict) -> dict:
    """Clean the preview of every part; pattern["preview"] = the first usable one."""
    first = None
    for part in pattern.get("parts", []):
        part["preview"] = normalize_preview(part.get("preview"))
        first = first or part["preview"]
    # older patterns had one preview for the whole pattern
    pattern["preview"] = first or normalize_preview(pattern.get("preview"))
    return pattern


def _parse_json(text: str) -> dict:
    """Claude is asked for pure JSON; ignore code fences or text around it."""
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise json.JSONDecodeError("No JSON object found", text, 0)
    return json.loads(text[start:end + 1])


def generate_instructions(artwork: dict, image_url: str, kind: str = "amigurumi",
                          model_info: dict = None, chart: dict = None,
                          yarn_weight: str = DEFAULT_YARN, colors: int = 6) -> dict:
    """
    kind = "amigurumi" (3D) or "tapestry" (2D, needs `chart`).
    yarn_weight = a key of YARN_WEIGHTS, colors = max. number of yarn colours.
    Returns the crochet pattern as a dict (see SYSTEM_PROMPT for its shape).
    """
    import anthropic

    if kind not in ("amigurumi", "tapestry"):
        raise ValueError("kind must be 'amigurumi' or 'tapestry'")
    if kind == "tapestry" and not chart:
        raise ValueError("A tapestry pattern needs the colour chart.")
    if yarn_weight not in YARN_WEIGHTS:
        raise ValueError(f"Unknown yarn weight: {yarn_weight}")

    api_key = get_api_key()
    if not api_key:
        raise ValueError("No Anthropic API key configured.")
    client = anthropic.Anthropic(api_key=api_key)
    messages = [{
        "role": "user",
        "content": [
            {"type": "image", "source": {"type": "url", "url": image_url}},
            {"type": "text", "text": _artwork_text(artwork, kind, model_info, chart, yarn_weight, colors)},
        ],
    }]

    # Up to two tries: if the answer is cut off or not valid JSON, ask once more
    # for a shorter, valid answer.
    for attempt in range(2):
        message = client.messages.create(
            model=CLAUDE_MODEL, max_tokens=MAX_TOKENS, system=SYSTEM_PROMPT, messages=messages,
        )
        text = "".join(block.text for block in message.content if block.type == "text")
        cut_off = message.stop_reason == "max_tokens"
        try:
            if cut_off:
                raise json.JSONDecodeError("Answer was cut off (max_tokens)", text, len(text))
            pattern = _parse_json(text)
            break
        except json.JSONDecodeError as exc:
            if attempt == 1:
                reason = "the answer was too long and got cut off" if cut_off else "the answer was not valid JSON"
                raise ValueError(f"Claude could not write the pattern ({reason}). Start: {text[:200]}") from exc
            messages = messages + [
                {"role": "assistant", "content": text or "(empty)"},
                {"role": "user", "content": (
                    "That answer was " + ("cut off because it was too long" if cut_off else "not valid JSON")
                    + ". Write the complete pattern again as valid JSON only, in the same shape, "
                    "and make it shorter: fewer parts, combine identical rounds, simplify details."
                )},
            ]

    pattern["pattern_type"] = kind
    if kind == "amigurumi":
        apply_previews(pattern)
    else:
        pattern.pop("preview", None)
        for part in pattern.get("parts", []):
            part.pop("preview", None)
    pattern["yarn_weight"] = YARN_WEIGHTS[yarn_weight]["label"]
    if kind == "tapestry":
        from app.services.chart2d_service import row_instructions
        pattern["chart_rows"] = row_instructions(chart)
    pattern["check"] = check_stitch_counts(pattern)
    pattern["source"] = {
        "title": artwork.get("title"),
        "artists": artwork.get("artists"),
        "uri": artwork.get("uri"),
        "credit": "Stiftung für Kunst, Kultur und Geschichte (SKKG), Winterthur. "
                  "Check the image's rights statement before publishing.",
    }
    return pattern


def check_stitch_counts(pattern: dict) -> list:
    """Simple sanity check: every step needs a positive stitch count."""
    problems = []
    for part in pattern.get("parts", []):
        for step in part.get("steps", []):
            count = step.get("stitch_count")
            if not isinstance(count, int) or count <= 0:
                problems.append(f"{part.get('name')} {step.get('step')}: missing stitch count")
    return problems


def to_markdown(pattern: dict) -> str:
    """Readable version of the pattern (for the demo, or to show as text)."""
    out = [f"# {pattern.get('title', 'Crochet pattern')}", ""]
    source = pattern.get("source", {})
    if source:
        out += [f"*Inspired by «{source.get('title')}» – {source.get('artists') or 'unknown artist'}*",
                f"*{source.get('credit')}*", ""]
    out += [f"**Type:** {pattern.get('pattern_type')}  ",
            f"**Difficulty:** {pattern.get('difficulty')}  ",
            f"**Finished size:** {pattern.get('finished_size_cm')} cm", ""]
    if pattern.get("yarn_note"):
        out += [f"> {pattern['yarn_note']}", ""]

    materials = pattern.get("materials", {})
    out.append("## Materials")
    for yarn in materials.get("yarn", []):
        out.append(f"- Yarn {yarn.get('color')} ({yarn.get('hex')}), about {yarn.get('amount_g')} g")
    out.append(f"- Hook {materials.get('hook_mm')} mm")
    out += [f"- {item}" for item in materials.get("other", [])]
    out.append("")

    out.append("## Abbreviations")
    out += [f"- **{k}**: {v}" for k, v in pattern.get("abbreviations", {}).items()]
    out.append("")

    for part in pattern.get("parts", []):
        out.append(f"## {part.get('name')} ({part.get('color')})")
        for step in part.get("steps", []):
            out.append(f"- **{step.get('step')}:** {step.get('instruction')} ({step.get('stitch_count')})")
        out.append("")

    if pattern.get("chart_rows"):
        out.append("## Chart rows")
        out.append("Row 1 is the bottom row of the chart. Odd rows right to left, "
                   "even rows left to right. Numbers are stitches, letters are colours.")
        out.append("")
        for row in pattern["chart_rows"]:
            out.append(f"- **Row {row['row']}** ({row['direction']}): "
                       f"{row['runs']} ({row['stitch_count']})")
        out.append("")

    if pattern.get("assembly"):
        out.append("## Assembly")
        out += [f"{i}. {s}" for i, s in enumerate(pattern["assembly"], 1)]
        out.append("")
    if pattern.get("notes"):
        out += ["## Notes", pattern["notes"], ""]
    return "\n".join(out)