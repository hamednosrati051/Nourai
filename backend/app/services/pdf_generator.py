"""Persian RTL PDF generation with Vazirmatn font.

Takes AI-generated structured text and renders a clean, right-to-left PDF.
"""
from __future__ import annotations

import io
import os
import re

import arabic_reshaper
from bidi.algorithm import get_display
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_RIGHT

_FONTS_DIR = os.path.join(os.path.dirname(__file__), "..", "assets", "fonts")
_FONTS_REGISTERED = False


def _ensure_fonts() -> None:
    global _FONTS_REGISTERED
    if _FONTS_REGISTERED:
        return
    regular = os.path.join(_FONTS_DIR, "Vazirmatn-Regular.ttf")
    bold = os.path.join(_FONTS_DIR, "Vazirmatn-Bold.ttf")
    pdfmetrics.registerFont(TTFont("Vazirmatn", regular))
    pdfmetrics.registerFont(TTFont("Vazirmatn-Bold", bold))
    _FONTS_REGISTERED = True


def _rtl(text: str) -> str:
    """Reshape + bidi for correct Persian rendering in reportlab."""
    if not text.strip():
        return ""
    reshaped = arabic_reshaper.reshape(text)
    return get_display(reshaped)


def _parse_blocks(text: str) -> list[tuple[str, str]]:
    """Split AI output into (kind, content) blocks.

    Kinds: 'h1' (title), 'h2' (section heading), 'p' (paragraph),
    'li' (list item).
    """
    blocks: list[tuple[str, str]] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("## "):
            blocks.append(("h2", line[3:].strip()))
        elif line.startswith("# "):
            blocks.append(("h1", line[2:].strip()))
        elif line.startswith(("- ", "* ", "• ")):
            blocks.append(("li", line[2:].strip()))
        elif re.match(r"^\d+[.)]\s", line):
            blocks.append(("li", re.sub(r"^\d+[.)]\s", "", line)))
        else:
            blocks.append(("p", line))
    return blocks


def generate_pdf(title: str, body_text: str) -> bytes:
    """Render a Persian RTL PDF. Returns PDF bytes."""
    _ensure_fonts()

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        rightMargin=2 * cm,
        leftMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
        title=title,
    )

    s_title = ParagraphStyle("Title2", fontName="Vazirmatn-Bold", fontSize=20,
                             leading=28, alignment=TA_RIGHT, spaceAfter=12)
    s_h2 = ParagraphStyle("H2", fontName="Vazirmatn-Bold", fontSize=14,
                          leading=22, alignment=TA_RIGHT,
                          spaceBefore=14, spaceAfter=6, textColor="#1e40af")
    s_p = ParagraphStyle("P", fontName="Vazirmatn", fontSize=11,
                         leading=20, alignment=TA_RIGHT, spaceAfter=8)
    s_li = ParagraphStyle("LI", fontName="Vazirmatn", fontSize=11,
                          leading=20, alignment=TA_RIGHT, spaceAfter=4,
                          rightIndent=12, bulletIndent=0)

    story = []
    story.append(Paragraph(_rtl(title), s_title))
    story.append(Spacer(1, 6))

    for kind, content in _parse_blocks(body_text):
        content = _rtl(content)
        if kind == "h1":
            story.append(Paragraph(content, s_title))
        elif kind == "h2":
            story.append(Paragraph(content, s_h2))
        elif kind == "li":
            story.append(Paragraph(f"• {content}", s_li))
        else:
            story.append(Paragraph(content, s_p))

    doc.build(story)
    return buf.getvalue()
