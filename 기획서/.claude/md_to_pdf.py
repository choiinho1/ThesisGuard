import sys
import re
import markdown
from bs4 import BeautifulSoup, NavigableString, Tag

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, ListFlowable, ListItem, KeepTogether
)
from reportlab.lib.enums import TA_LEFT

FONT_DIR = r"C:\Windows\Fonts"
pdfmetrics.registerFont(TTFont("Malgun", FONT_DIR + r"\malgun.ttf"))
pdfmetrics.registerFont(TTFont("Malgun-Bold", FONT_DIR + r"\malgunbd.ttf"))
pdfmetrics.registerFontFamily("Malgun", normal="Malgun", bold="Malgun-Bold",
                               italic="Malgun", boldItalic="Malgun-Bold")

styles = getSampleStyleSheet()


def style(name, size, leading, bold=False, space_before=0, space_after=6, text_color="#111111"):
    return ParagraphStyle(
        name, parent=styles["Normal"],
        fontName="Malgun-Bold" if bold else "Malgun",
        fontSize=size, leading=leading,
        spaceBefore=space_before, spaceAfter=space_after,
        textColor=colors.HexColor(text_color),
        alignment=TA_LEFT,
    )


S_TITLE = style("title", 20, 26, bold=True, space_after=4)
S_QUOTE = style("quote", 9.5, 14, space_after=14, text_color="#555555")
S_H1 = style("h1", 15, 20, bold=True, space_before=16, space_after=8, text_color="#1a1a1a")
S_H2 = style("h2", 12.5, 17, bold=True, space_before=12, space_after=6, text_color="#1a1a1a")
S_H3 = style("h3", 11, 15, bold=True, space_before=8, space_after=4, text_color="#1a1a1a")
S_BODY = style("body", 9.5, 14, space_after=6)
S_LI = style("li", 9.5, 14, space_after=3)
S_CELL = style("cell", 8.5, 12, space_after=0)
S_CELL_HEAD = style("cellhead", 8.5, 12, bold=True, space_after=0)
S_CODE = ParagraphStyle("code", parent=S_BODY, fontName="Malgun", fontSize=8, leading=11,
                         backColor=colors.HexColor("#f4f4f4"))


def inline_to_html(tag):
    """Convert inline children (b, code, em) of a tag to a reportlab-markup string."""
    out = []
    for child in tag.children:
        if isinstance(child, NavigableString):
            out.append(str(child).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
        elif isinstance(child, Tag):
            if child.name in ("strong", "b"):
                out.append(f"<b>{inline_to_html(child)}</b>")
            elif child.name in ("em", "i"):
                out.append(f"<i>{inline_to_html(child)}</i>")
            elif child.name == "code":
                out.append(f'<font face="Malgun" color="#a33d1f">{inline_to_html(child)}</font>')
            elif child.name == "a":
                out.append(inline_to_html(child))
            elif child.name == "br":
                out.append("<br/>")
            else:
                out.append(inline_to_html(child))
    text = "".join(out)
    text = re.sub(r"\n+", " ", text).strip()
    return text


def build_table(table_tag):
    rows = []
    for tr in table_tag.find_all("tr"):
        cells = tr.find_all(["td", "th"])
        row = []
        for c in cells:
            is_head = c.name == "th"
            p = Paragraph(inline_to_html(c) or "&nbsp;", S_CELL_HEAD if is_head else S_CELL)
            row.append(p)
        rows.append(row)
    if not rows:
        return None
    ncols = max(len(r) for r in rows)
    for r in rows:
        while len(r) < ncols:
            r.append(Paragraph("", S_CELL))

    avail_width = 170 * mm
    col_width = avail_width / ncols
    t = Table(rows, colWidths=[col_width] * ncols, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8eef7")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#bbbbbb")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f7f9fc")]),
    ]))
    return t


def build_list(list_tag, ordered=False):
    items = []
    for i, li in enumerate(list_tag.find_all("li", recursive=False), start=1):
        sub_flowables = []
        text_parts = []
        for child in li.children:
            if isinstance(child, Tag) and child.name in ("ul", "ol"):
                if text_parts:
                    sub_flowables.append(Paragraph("".join(text_parts).strip(), S_LI))
                    text_parts = []
                sub_flowables.append(build_list(child, ordered=(child.name == "ol")))
            elif isinstance(child, Tag):
                text_parts.append(inline_to_html(child))
            elif isinstance(child, NavigableString):
                text_parts.append(str(child))
        if text_parts:
            joined = re.sub(r"\s+", " ", "".join(text_parts)).strip()
            sub_flowables.insert(0, Paragraph(joined, S_LI))
        bullet = f"{i}." if ordered else "•"
        items.append(ListItem(sub_flowables if len(sub_flowables) > 1 else (sub_flowables[0] if sub_flowables else Paragraph("", S_LI)),
                               leftIndent=12, value=bullet, bulletColor=colors.HexColor("#333333")))
    return ListFlowable(items, bulletType="bullet", start=None, leftIndent=14, spaceBefore=2, spaceAfter=6)


def build_blockquote(bq_tag):
    flow = []
    for child in bq_tag.find_all(["p"], recursive=False):
        flow.append(Paragraph(inline_to_html(child), style("bq", 9, 13, space_after=4, text_color="#444444")))
    tbl = Table([[f] for f in flow] if flow else [[Paragraph(inline_to_html(bq_tag), S_BODY)]],
                colWidths=[168 * mm])
    tbl.setStyle(TableStyle([
        ("LINEBEFORE", (0, 0), (0, -1), 2.5, colors.HexColor("#9db4d1")),
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f2f5fa")),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    return tbl


def build_pre(pre_tag):
    code_text = pre_tag.get_text()
    lines = code_text.split("\n")
    html_lines = "<br/>".join(
        l.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace(" ", "&nbsp;")
        for l in lines
    )
    p = Paragraph(html_lines, S_CODE)
    tbl = Table([[p]], colWidths=[168 * mm])
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f4f4f4")),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#dddddd")),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    return tbl


def md_to_pdf(md_path, pdf_path, title_override=None):
    with open(md_path, "r", encoding="utf-8") as f:
        md_text = f.read()

    html = markdown.markdown(md_text, extensions=["tables", "fenced_code", "sane_lists"])
    soup = BeautifulSoup(html, "html.parser")

    story = []
    first_h1_done = False

    for el in soup.find_all(recursive=False):
        if el.name == "h1":
            txt = inline_to_html(el)
            if not first_h1_done:
                story.append(Paragraph(txt, S_TITLE))
                story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#cccccc"), spaceAfter=10))
                first_h1_done = True
            else:
                story.append(Paragraph(txt, S_H1))
        elif el.name == "h2":
            story.append(Paragraph(inline_to_html(el), S_H2))
        elif el.name == "h3":
            story.append(Paragraph(inline_to_html(el), S_H3))
        elif el.name == "h4":
            story.append(Paragraph(inline_to_html(el), S_H3))
        elif el.name == "table":
            t = build_table(el)
            if t:
                story.append(KeepTogether([t, Spacer(1, 8)]))
        elif el.name == "ul":
            story.append(build_list(el, ordered=False))
        elif el.name == "ol":
            story.append(build_list(el, ordered=True))
        elif el.name == "blockquote":
            story.append(build_blockquote(el))
            story.append(Spacer(1, 6))
        elif el.name == "pre":
            story.append(build_pre(el))
            story.append(Spacer(1, 8))
        elif el.name == "hr":
            story.append(Spacer(1, 4))
            story.append(HRFlowable(width="100%", thickness=0.75, color=colors.HexColor("#dddddd")))
            story.append(Spacer(1, 8))
        elif el.name == "p":
            txt = inline_to_html(el)
            if not txt:
                continue
            is_quote_line = txt.startswith("&gt;") or txt.startswith(">")
            story.append(Paragraph(txt, S_BODY))
        else:
            txt = inline_to_html(el) if hasattr(el, "children") else str(el)
            if txt.strip():
                story.append(Paragraph(txt, S_BODY))

    doc = SimpleDocTemplate(
        pdf_path, pagesize=A4,
        leftMargin=20 * mm, rightMargin=20 * mm,
        topMargin=16 * mm, bottomMargin=16 * mm,
        title=title_override or md_path,
    )
    doc.build(story)
    print(f"OK: {pdf_path}")


if __name__ == "__main__":
    pairs = sys.argv[1:]
    for i in range(0, len(pairs), 2):
        md_to_pdf(pairs[i], pairs[i + 1])
