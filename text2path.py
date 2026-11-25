"""Turn a text string into SVG <path> outlines using Unbounded at an exact weight."""
from functools import lru_cache
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
import uharfbuzz as hb

@lru_cache(maxsize=None)
def _load(path, wght):
    static = instantiateVariableFont(TTFont(path), {"wght": wght})
    hbfont = hb.Font(hb.Face(open(path, "rb").read()))
    hbfont.set_variations({"wght": wght})
    return static, hbfont

def text_path(text, x, y, size, wght, font_path, fill="#000"):
    static, hbfont = _load(font_path, wght)
    upem = static["head"].unitsPerEm
    scale = size / upem
    buf = hb.Buffer(); buf.add_str(text); buf.guess_segment_properties()
    hb.shape(hbfont, buf, {"kern": True, "liga": True})
    glyphset = static.getGlyphSet(); order = static.getGlyphOrder()
    pen = SVGPathPen(glyphset)
    cx = 0
    for info, pos in zip(buf.glyph_infos, buf.glyph_positions):
        tp = TransformPen(pen, (scale, 0, 0, -scale, x + (cx + pos.x_offset) * scale, y - pos.y_offset * scale))
        glyphset[order[info.codepoint]].draw(tp)
        cx += pos.x_advance
    return f'<path fill="{fill}" d="{pen.getCommands()}"/>'


def text_width(text, size, wght, font_path):
    """Ширина рядка в пікселях (для підкладок і значків поруч із текстом)."""
    static, hbfont = _load(font_path, wght)
    buf = hb.Buffer(); buf.add_str(text); buf.guess_segment_properties()
    hb.shape(hbfont, buf, {"kern": True, "liga": True})
    return sum(p.x_advance for p in buf.glyph_positions) * size / static["head"].unitsPerEm
