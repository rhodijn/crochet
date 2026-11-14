"""
Crochet instructions for an artwork, written by Claude from the artwork image.
Two kinds, made for every artwork:
  - "amigurumi": 3D figure, uses the proportions of the 3D model if available
  - "tapestry":  2D picture, built on the colour chart from chart2d_service

Requires:  pip install anthropic
           ANTHROPIC_API_KEY environment variable
"""
import json
import os

CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-5-5")
MAX_TOKENS = 8000

SYSTEM_PROMPT = """You are an experienced crochet designer. You turn artworks from a
museum collection into crochet patterns that a hobby crocheter can actually follow.

Rules:
- Use US crochet terms and explain every abbreviation you use.
- Write the kind of pattern the request asks for (amigurumi or tapestry).
- Every round/row must state its stitch count, and the counts must add up.
- Keep it achievable: about 2 to 6 parts, at most 6 yarn colors.

Answer with JSON only, no other text, in exactly this shape:
{
  "title": "pattern name",
  "pattern_type": "amigurumi" or "tapestry",
  "difficulty": "beginner" | "intermediate" | "advanced",
  "finished_size_cm": "e.g. 15 x 10 x 8",
  "materials": {
    "yarn": [{"color": "name", "hex": "#rrggbb", "amount_g": 20}],
    "hook_mm": 3.0,
    "other": ["stuffing", "safety eyes"]
  },
  "abbreviations": {"sc": "single crochet"},
  "parts": [
    {"name": "Body", "color": "name",
     "steps": [{"step": "R1", "instruction": "6 sc in magic ring", "stitch_count": 6}]}
  ],
  "assembly": ["how to put the parts together"],
  "notes": "short tips"
}"""


AMIGURUMI_TASK = (
    "Write an AMIGURUMI pattern (a 3D crocheted figure, worked in rounds) of the "
    "main subject of this artwork. If the artwork is flat (a painting or drawing), "
    "turn its main figure or object into a 3D figure."
)

TAPESTRY_TASK = (
    "Write a TAPESTRY CROCHET pattern (a flat picture in single crochet, worked in rows). "
    "The colour chart is already computed and its row-by-row colour runs will be printed "
    "after your text, so do NOT write the picture rows yourself. Use exactly the chart's "
    "colours as the yarn list (keep the letters A, B, C ... and their hex values, give each "
    "a yarn colour name, estimate grams from the stitch counts). In 'parts' describe only "
    "the work around the chart: foundation chain, how to read the chart, how to change "
    "colours and carry yarn, and a simple border. "
)


def _artwork_text(artwork: dict, kind: str, model_info: dict = None, chart: dict = None) -> str:
    lines = [
        AMIGURUMI_TASK if kind == "amigurumi" else TAPESTRY_TASK,
        "The artwork is from the SKKG collection.",
        f"Title: {artwork.get('title') or 'unknown'}",
        f"Artist: {artwork.get('artists') or 'unknown'}",
        f"Date: {artwork.get('date') or 'unknown'}",
        f"Gattung (type): {artwork.get('gattung') or 'unknown'}",
        f"Material/technique: {artwork.get('material') or 'unknown'}",
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


def _parse_json(text: str) -> dict:
    """Claude is asked for pure JSON; strip code fences just in case."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1].rsplit("```", 1)[0]
    return json.loads(cleaned)


def generate_instructions(artwork: dict, image_url: str, kind: str = "amigurumi",
                          model_info: dict = None, chart: dict = None) -> dict:
    """
    kind = "amigurumi" (3D) or "tapestry" (2D, needs `chart`).
    Returns the crochet pattern as a dict (see SYSTEM_PROMPT for its shape).
    """
    import anthropic

    if kind not in ("amigurumi", "tapestry"):
        raise ValueError("kind must be 'amigurumi' or 'tapestry'")
    if kind == "tapestry" and not chart:
        raise ValueError("A tapestry pattern needs the colour chart.")

    client = anthropic.Anthropic()   # reads ANTHROPIC_API_KEY
    message = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=MAX_TOKENS,
        system=SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "url", "url": image_url}},
                {"type": "text", "text": _artwork_text(artwork, kind, model_info, chart)},
            ],
        }],
    )
    text = "".join(block.text for block in message.content if block.type == "text")
    try:
        pattern = _parse_json(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Claude did not return valid JSON: {text[:300]}") from exc

    pattern["pattern_type"] = kind
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