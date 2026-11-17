"""Render UPSET's matchup summary using the selected cutoff and stats window."""

from datetime import date
from io import BytesIO
from pathlib import Path

from matplotlib import get_data_path
from PIL import Image, ImageDraw, ImageFont, ImageOps

FONT_DIR = Path(get_data_path()) / "fonts/ttf"
INK = "#f4f5f7"
SECONDARY = "#c1b7b5"
BORDER = "#392e2e"
CORNERS = (("#ff737d", "#2a191c"), ("#83b6ff", "#171f2e"))


def font(size, bold=True):
    name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    return ImageFont.truetype(str(FONT_DIR / name), size)


def fit_text(draw, value, maximum, initial):
    for size in range(initial, 13, -1):
        candidate = font(size)
        if draw.textlength(value, font=candidate) <= maximum:
            return candidate
    return font(13)


def record_text(wins, losses, draws, nc):
    return f"{wins}–{losses}" + (f"–{draws}" if draws else "") + (f", {nc} NC" if nc else "")


def ufc_record(fighter):
    summary = fighter["summary"]
    career = summary["career"]
    return record_text(career["win"], career["loss"], summary["draws"], summary["no_contests"])


def pro_record(fighter):
    record = fighter.get("professional_record")
    return record_text(record["wins"], record["losses"], record["draws"], record["no_contests"]) if record else "—"


def tape(fighter):
    height = fighter["profile"].get("height_inches")
    reach = fighter["profile"].get("reach_inches")
    feet, inches = divmod(round(height), 12) if height is not None else (None, None)
    return (f"{feet}′ {inches}″" if feet is not None else "—") + " / " + (f"{reach:g}″" if reach is not None else "—")


def rate(fighter, key, percent=False):
    value = fighter["metrics"].get(key)
    if value is None:
        return "—"
    return f"{value:.0%}" if percent else f"{value:.2f}"


def fighter_header(draw, canvas, fighter, portrait, index):
    left = 38 + 584 * index
    accent, surface = CORNERS[index]
    draw.rectangle((left, 92, left + 540, 245), fill=surface, outline=BORDER)
    draw.rectangle((left, 92, left + 540, 94), fill=accent)
    draw.rectangle((left + 14, 107, left + 143, 230), fill="#101014")
    asset = None
    if portrait is not None:
        try:
            with Image.open(portrait) as image:
                asset = ImageOps.contain(image.convert("RGBA"), (129, 123), Image.Resampling.NEAREST)
        except (OSError, Image.DecompressionBombError):
            pass
    if asset is not None:
        canvas.paste(asset, (left + 14 + (129 - asset.width) // 2, 107 + (123 - asset.height) // 2), asset)
    else:
        initials = "".join(name[0] for name in fighter["name"].split()[:2]).upper()
        draw.text((left + 79, 169), initials, font=font(38), fill=accent, anchor="mm")
    text_left = left + 161
    draw.text((text_left, 118), ("RED CORNER", "BLUE CORNER")[index], font=font(14), fill=accent)
    name = fighter["name"].upper()
    draw.text((text_left, 148), name, font=fit_text(draw, name, 365, 34), fill=INK)
    score = fighter.get("rating", {}).get("score")
    if score is not None:
        draw.text((text_left, 203), f"{score}  EXPERIMENTAL UPSET RATING", font=font(15), fill=SECONDARY)


def matchup_png(fighters, portraits, before, window):
    canvas = Image.new("RGB", (1200, 630), "#0f0d0d")
    draw = ImageDraw.Draw(canvas)
    draw.rectangle((0, 0, 599, 4), fill="#e63946")
    draw.rectangle((600, 0, 1199, 4), fill="#3a86ff")
    draw.text((38, 24), "UPSET", font=font(38), fill=INK)
    draw.text((191, 45), "MATCHUP REPORT", font=font(15), fill=SECONDARY)
    cutoff = date.fromisoformat(before).strftime("%b %d, %Y").replace(" 0", " ")
    draw.text((1162, 40), f"BEFORE {cutoff.upper()}", font=font(17), fill=INK, anchor="rt")
    for index, (fighter, portrait) in enumerate(zip(fighters, portraits, strict=True)):
        fighter_header(draw, canvas, fighter, portrait, index)
    draw.ellipse((580, 151, 620, 191), fill="#0f0d0d", outline=BORDER, width=2)
    draw.text((600, 171), "VS", font=font(14), fill=INK, anchor="mm")

    tape_rows = [("UFC record", ufc_record), ("Height / reach", tape)]
    if any(fighter.get("professional_record") for fighter in fighters):
        tape_rows.insert(1, ("Pro MMA record", pro_record))
    stat_rows = [
        ("Fights with stats", lambda fighter: str(fighter["metrics"]["bouts"])),
        ("Sig. strikes landed / absorbed per min", lambda fighter: " / ".join(
            rate(fighter, key) for key in ("sig_landed_per_minute", "sig_absorbed_per_minute"))),
        ("Takedowns landed / 15 min", lambda fighter: rate(fighter, "takedowns_per_15_minutes")),
        ("Takedown defense", lambda fighter: rate(fighter, "takedown_defense", percent=True)),
    ]
    y = 265
    for label, rows in (("TALE OF THE TAPE", tape_rows), ("RECORDED UFC STATS", stat_rows)):
        draw.text((38, y), label, font=font(14), fill=SECONDARY)
        y += 23
        for name, value in rows:
            draw.rectangle((38, y, 1162, y + 33), fill="#181414", outline=BORDER)
            draw.text((600, y + 17), name, font=font(16, False), fill=SECONDARY, anchor="mm")
            for x, fighter, (accent, _) in zip((290, 910), fighters, CORNERS, strict=True):
                display = value(fighter)
                draw.text((x, y + 17), display, font=fit_text(draw, display, 350, 19), fill=accent, anchor="mm")
            y += 34
        y += 11

    window_label = f"Last {window} UFC fights with stats" if window else "Career UFC stats"
    draw.line((38, 579, 1162, 579), fill=BORDER)
    draw.text((38, 597), window_label, font=font(15), fill=INK)
    draw.text((1162, 597), "Records and ratings use all available history before the cutoff", font=font(14, False),
              fill=SECONDARY, anchor="rt")
    buffer = BytesIO()
    canvas.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()
