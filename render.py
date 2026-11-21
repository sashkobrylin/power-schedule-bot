"""Заповнює SVG-шаблон і робить PNG. Увесь текст перетворюється на криві, тому шрифти на сервері не потрібні."""
import re
from pathlib import Path
from xml.sax.saxutils import unescape

from text2path import text_path

ROOT = Path(__file__).parent
TEMPLATE = ROOT / "template" / "light-info.svg"
FONT = str(ROOT / "fonts" / "Unbounded-VariableFont_wght.ttf")

MONTHS = ["січня", "лютого", "березня", "квітня", "травня", "червня",
          "липня", "серпня", "вересня", "жовтня", "листопада", "грудня"]

# Розміри й положення — підібрані за оригінальними кривими з макета
TITLE = dict(x=91, y=106.9, size=40, wght=400)
HOURS = dict(xs=(120.5, 595.6), y=601.2, step=42, size=30, wght=400, max_lines=4)


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


def _hour_lines(x, lines, empty_text):
    lines = lines or [empty_text]
    n = len(lines)
    size, step = HOURS["size"], HOURS["step"]
    if n > HOURS["max_lines"]:  # якщо проміжків багато — стискаємо, щоб влізли в ту саму висоту
        k = HOURS["max_lines"] / n
        size, step = size * k, step * k
    y0 = HOURS["y"] - (HOURS["size"] - size) * 0.75  # щоб верх першого рядка лишався на місці
    return "".join(text_path(t, x, y0 + step * i, size, HOURS["wght"], FONT) for i, t in enumerate(lines))


def build_svg(title, date, hours1, hours2, empty_text):
    svg = TEMPLATE.read_text(encoding="utf-8")
    svg = _outline_texts(svg, {"date": f"{date.day} {MONTHS[date.month - 1]}"})
    svg = _replace_group(svg, "title", text_path(title, TITLE["x"], TITLE["y"], TITLE["size"], TITLE["wght"], FONT))
    svg = _replace_group(svg, "hours1", _hour_lines(HOURS["xs"][0], hours1, empty_text))
    svg = _replace_group(svg, "hours2", _hour_lines(HOURS["xs"][1], hours2, empty_text))
    return svg


def svg_to_png(svg, out_path):
    from playwright.sync_api import sync_playwright
    w, h = map(float, re.search(r'viewBox="0 0 ([\d.]+) ([\d.]+)"', svg).groups())
    html = f'<html><body style="margin:0">{svg.replace("<svg ", f"<svg width={chr(34)}{w}{chr(34)} height={chr(34)}{h}{chr(34)} ", 1)}</body></html>'
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": int(w), "height": int(h)})
        page.set_content(html)
        page.screenshot(path=str(out_path), clip={"x": 0, "y": 0, "width": w, "height": h})
        browser.close()
