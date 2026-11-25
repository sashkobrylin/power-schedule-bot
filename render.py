"""Заповнює SVG-шаблон і робить PNG. Увесь текст перетворюється на криві, тому шрифти на сервері не потрібні."""
import re
from pathlib import Path
from xml.sax.saxutils import unescape

from text2path import text_path, text_width

ROOT = Path(__file__).parent
TEMPLATE = ROOT / "template" / "light-info.svg"
FONT = str(ROOT / "fonts" / "Unbounded-VariableFont_wght.ttf")

MONTHS = ["січня", "лютого", "березня", "квітня", "травня", "червня",
          "липня", "серпня", "вересня", "жовтня", "листопада", "грудня"]

# Розміри й положення — підібрані за оригінальними кривими з макета
TITLE = dict(x=90.71, y=106.9, size=40, wght=400)
HOURS = dict(xs=(120.66, 595.79), y=624.17, step=42, size=30, wght=400, max_lines=4)
UPDATE = dict(x=93.85, y=313.73, size=27, wght=400, fill="#97a3d1")  # «Станом на …»


def _css_classes(svg):
    style = re.search(r"<style>(.*?)</style>", svg, re.S).group(1)
    classes = {}
    for sel, body in re.findall(r"([^{}]+)\{([^}]*)\}", style):
        props = dict((k.strip(), v.strip()) for k, v in
                     (p.split(":", 1) for p in body.split(";") if ":" in p))
        for name in re.findall(r"\.(\w+)", sel):
            classes.setdefault(name, {}).update(props)
    return classes


def _outline_texts(svg, overrides):
    """Замінює кожен <text> кривими. overrides: {id: новий текст}."""
    classes = _css_classes(svg)

    def repl(m):
        attrs, body = m.group(1), m.group(2)
        style = {}
        for c in re.search(r'class="([^"]*)"', attrs).group(1).split():
            style.update(classes.get(c, {}))
        size = float(style.get("font-size", "16px").rstrip("px"))
        wght = int(style.get("font-weight", "400"))
        fill = style.get("fill", "#000")
        tx, ty = map(float, re.search(r"translate\(([\d.-]+)[ ,]+([\d.-]+)\)", attrs).groups())
        tid = re.search(r'id="([^"]+)"', attrs)
        tid = tid.group(1) if tid else None
        spans = re.findall(r'<tspan x="([\d.-]+)" y="([\d.-]+)">(.*?)</tspan>', body, re.S)
        if tid in overrides:
            spans = [(spans[0][0], spans[0][1], overrides[tid])]
        paths = "".join(text_path(unescape(t).rstrip(), tx + float(x), ty + float(y), size, wght, FONT, fill)
                        for x, y, t in spans)
        return f'<g{" id=" + chr(34) + tid + chr(34) if tid else ""}>{paths}</g>'

    return re.sub(r"<text([^>]*)>(.*?)</text>", repl, svg, flags=re.S)


def _replace_group(svg, gid, inner):
    i = svg.index(f'<g id="{gid}">')
    j = svg.index("</g>", i)
    return svg[:i] + f'<g id="{gid}">' + inner + svg[j:]


# Як позначати зміни в оновленому графіку
MARK = dict(style="marker", new_bg="#fff170", new_fg="#f68006", removed="#a3a3a3")


def diff_lines(current, previous):
    """[(текст, вид)], де вид: same / new / removed. previous=None — графік новий, нічого не позначаємо."""
    if previous is None:
        return [(t, "same") for t in current]
    items = [(t, "same" if t in previous else "new") for t in current]
    items += [(t, "removed") for t in previous if t not in current]
    return sorted(items, key=lambda it: (it[0][:7], it[1] == "removed", it[0]))  # за часом; скасований — під новим


def _hour_lines(x, items, empty_text, style=None):
    style = style or MARK["style"]
    items = [(t, "same") if isinstance(t, str) else t for t in items]
    removed_any = any(k == "removed" for _, k in items)
    if style == "marker":  # у цьому стилі скасовані проміжки не показуємо
        items = [it for it in items if it[1] != "removed"]
    if not any(k != "removed" for _, k in items):  # світло не вимикатимуть
        items = [(empty_text, "new" if removed_any else "same")] + items
    n = len(items)
    size, step = HOURS["size"], HOURS["step"]
    if n > HOURS["max_lines"]:  # якщо проміжків багато — стискаємо, щоб влізли в ту саму висоту
        k = HOURS["max_lines"] / n
        size, step = size * k, step * k
    y0 = HOURS["y"] - (HOURS["size"] - size) * 0.75  # щоб верх першого рядка лишався на місці
    out = []
    for i, (t, kind) in enumerate(items):
        y = y0 + step * i
        w = text_width(t, size, HOURS["wght"], FONT)
        fill = "#000"
        if kind == "removed":
            fill = MARK["removed"]
            out.append(f'<rect x="{x - 2}" y="{y - size * 0.40}" width="{w + 4}" height="{size * 0.08}" fill="{fill}"/>')
        elif kind == "new" and style in ("marker", "marker+strike"):
            pad = size * 0.25
            out.insert(0, f'<rect x="{x - pad}" y="{y - size * 0.95}" width="{w + 2 * pad}" height="{size * 1.3}" '
                          f'rx="{size * 0.3}" fill="{MARK['new_bg']}"/>')
        elif kind == "new" and style == "color":
            fill = MARK["new_fg"]
        out.append(text_path(t, x, y, size, HOURS["wght"], FONT, fill))
        if kind == "new" and style == "badge":
            bs = size * 0.5; bx = x + w + size * 0.4; label = "нове"
            bw = text_width(label, bs, 600, FONT) + bs * 1.2
            out.append(f'<rect x="{bx}" y="{y - size * 0.85}" width="{bw}" height="{bs * 1.7}" rx="{bs * 0.85}" fill="{MARK['new_fg']}"/>')
            out.append(text_path(label, bx + bs * 0.6, y - size * 0.85 + bs * 1.22, bs, 600, FONT, "#fff"))
    return "".join(out)


def build_svg(title, date, hours1, hours2, empty_text, style=None, updated_at=None):
    """updated_at — datetime, коли обленерго оновило графік (рядок «Станом на …»)."""
    svg = TEMPLATE.read_text(encoding="utf-8")
    svg = _outline_texts(svg, {"date": f"{date.day} {MONTHS[date.month - 1]}"})
    svg = _replace_group(svg, "title", text_path(title, TITLE["x"], TITLE["y"], TITLE["size"], TITLE["wght"], FONT))
    svg = _replace_group(svg, "hours1", _hour_lines(HOURS["xs"][0], hours1, empty_text, style))
    svg = _replace_group(svg, "hours2", _hour_lines(HOURS["xs"][1], hours2, empty_text, style))
    if updated_at is not None:
        text = f"Станом на {updated_at:%H:%M}, {updated_at:%d.%m.%Y}"
        svg = _replace_group(svg, "update_x5F_time", text_path(text, UPDATE["x"], UPDATE["y"], UPDATE["size"],
                                                                UPDATE["wght"], FONT, UPDATE["fill"]))
    return svg


def svg_to_png(svg, out_path, jpeg_path=None):
    from playwright.sync_api import sync_playwright
    w, h = map(float, re.search(r'viewBox="0 0 ([\d.]+) ([\d.]+)"', svg).groups())
    html = f'<html><body style="margin:0">{svg.replace("<svg ", f"<svg width={chr(34)}{w}{chr(34)} height={chr(34)}{h}{chr(34)} ", 1)}</body></html>'
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": int(w), "height": int(h)})
        page.set_content(html)
        clip = {"x": 0, "y": 0, "width": w, "height": h}
        page.screenshot(path=str(out_path), clip=clip)
        if jpeg_path:  # Viber приймає лише JPEG до 1 МБ
            page.screenshot(path=str(jpeg_path), clip=clip, type="jpeg", quality=90)
        browser.close()
