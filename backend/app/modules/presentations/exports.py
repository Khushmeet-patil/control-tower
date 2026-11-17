"""Review pack exports: PowerPoint (python-pptx), PDF (reportlab) and Excel (openpyxl).

All three are drawn from PresentationService.pack(), the same figures the presenter sees (live, or
from the snapshot), so no number is copied by hand. `widget_table()` turns each widget into a summary
line and a table, which every format then lays out in its own way. Speaker notes go to the notes pane
in PowerPoint and below each page in the PDF and Excel files.
"""
import re
from datetime import date
from io import BytesIO
from xml.sax.saxutils import escape

from app.core.models import utcnow
from app.modules.snapshots.exports import Labels, about_sheet, safe_append

PPTX = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
PDF = "application/pdf"
MAX_ROWS = 12
NAVY, MUTED, BORDER = "2F5D8A", "64748B", "E2E8F0"


def _fmt_date(v):
    return date.fromisoformat(v).strftime("%d %b %Y") if v else ""


def widget_table(widget, data, labels) -> dict:
    """{"title", "summary", "headers", "rows", "colors", "kind"} for one widget."""
    out = {"title": widget.get("title") or "", "kind": widget["type"], "summary": "", "headers": [], "rows": [],
           "colors": [], "chart": widget.get("chart") or "bar"}
    if not data or data.get("error"):
        out["summary"] = (data or {}).get("error") or "No figures"
        out["kind"] = "error"
        return out
    kind = widget["type"]
    item = lambda i: f"{i['code']} {i['title']}"  # noqa: E731
    if kind == "kpi":
        out["summary"] = f"{data['value']} item{'s' if data['value'] != 1 else ''}"
        out["value"] = data["value"]
    elif kind == "chart":
        out["headers"] = ["Group", "Items"]
        for g in data["groups"]:
            label, color = labels.group(data["group_by"], g)
            out["rows"].append([label, g["count"]])
            out["colors"].append(color)
        out["summary"] = f"{data['total']} items"
    elif kind == "progress":
        out["summary"] = f"Weighted average {data['average']}% across {data['counted']} item(s)"
        out["headers"] = ["Item", "Progress %"]
        out["rows"] = [[item(i), i["progress"]] for i in data["items"]]
    elif kind == "timeline":
        out["summary"] = f"{data['total']} items"
        out["headers"] = ["Item", "Planned start", "Planned finish", "Overdue"]
        out["rows"] = [[item(i), _fmt_date(i.get("planned_start")), _fmt_date(i["planned_end"]),
                        "Yes" if i.get("is_overdue") else ""] for i in data["items"]]
    elif kind == "table":
        out["summary"] = f"{data['total']} items" + (f", first {len(data['items'])} shown" if data["total"] > len(data["items"]) else "")
        out["headers"] = ["Item", "Health", "Status", "Accountable", "Progress %"]
        out["rows"] = [[item(i), labels.health_label((i.get("health") or {}).get("code")), labels.label(i.get("status_id")) or "",
                        (i.get("accountable") or {}).get("full_name") or "", i.get("progress", 0)] for i in data["items"]]
    elif kind == "capacity":
        out["summary"] = f"Free capacity {data['free_pct']} pts across {data['total']} people"
        out["headers"] = ["Person", "Load %", "Free %"]
        out["rows"] = [[r["person"]["full_name"], r["load_pct"], r["free_pct"]] for r in data["items"]]
    elif kind == "actions":
        out["headers"] = ["Item", "Why"]
        out["rows"] = [[f"{e['item']['code']} {e['item']['title']}", e.get("what") or ""] for e in data.get("entries", [])]
    return out


def _source(pack) -> str:
    p = pack["presentation"]
    if p["mode"] == "snapshot" and p["snapshot"]:
        s = p["snapshot"]
        return f"Figures from snapshot “{s['label']}” as of {_fmt_date(s['as_of'])} ({s['status']})"
    return f"Live figures, {utcnow():%d %b %Y %H:%M} UTC"


def _pages(pack, labels):
    for page in pack["pages"]:
        tables = [widget_table(w, page["data"].get(w["id"]), labels) for w in page["widgets"]]
        yield page["page"], tables, page.get("error")


def _hex(color, fallback=NAVY):
    color = (color or "").lstrip("#")
    return color.upper() if re.fullmatch(r"[0-9A-Fa-f]{6}", color) else fallback


# ---------------------------------------------------------------------- PowerPoint
def to_pptx(actor, pack) -> bytes:
    from pptx import Presentation as Deck
    from pptx.chart.data import CategoryChartData
    from pptx.dml.color import RGBColor
    from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION
    from pptx.util import Inches, Pt

    labels = Labels(actor.tenant_id)
    deck = Deck()
    deck.slide_width, deck.slide_height = Inches(13.333), Inches(7.5)
    first = deck.slides.add_slide(deck.slide_layouts[0])
    first.shapes.title.text = pack["presentation"]["name"]
    first.placeholders[1].text = _source(pack)

    def text(slide, x, y, w, h, value, size=12, bold=False, color=None):
        box = slide.shapes.add_textbox(x, y, w, h)
        frame = box.text_frame
        frame.word_wrap = True
        run = frame.paragraphs[0].add_run()
        run.text = str(value)
        run.font.size, run.font.bold = Pt(size), bold
        if color:
            run.font.color.rgb = RGBColor.from_string(color)
        return box

    cols, rows_per = 3, 2
    margin, top = Inches(0.5), Inches(1.3)
    cell_w = (deck.slide_width - 2 * margin) // cols
    cell_h = (deck.slide_height - top - Inches(0.3)) // rows_per
    for page, tables, error in _pages(pack, labels):
        chunks = [tables[i:i + cols * rows_per] for i in range(0, len(tables), cols * rows_per)] or [[]]
        for n, chunk in enumerate(chunks):
            slide = deck.slides.add_slide(deck.slide_layouts[6])
            text(slide, margin, Inches(0.3), deck.slide_width - 2 * margin, Inches(0.6),
                 page["title"] + (" (continued)" if n else ""), 26, True, NAVY)
            text(slide, margin, Inches(0.85), deck.slide_width - 2 * margin, Inches(0.35), _source(pack), 11, color=MUTED)
            if n == 0 and page.get("notes"):
                slide.notes_slide.notes_text_frame.text = page["notes"]
            if error:
                text(slide, margin, top, deck.slide_width - 2 * margin, Inches(1), error, 14)
            for i, t in enumerate(chunk):
                x = margin + (i % cols) * cell_w
                y = top + (i // cols) * cell_h
                w, h = cell_w - Inches(0.2), cell_h - Inches(0.2)
                text(slide, x, y, w, Inches(0.35), t["title"], 13, True)
                body_y, body_h = y + Inches(0.4), h - Inches(0.4)
                if t["kind"] == "kpi":
                    text(slide, x, body_y, w, Inches(1), t["value"], 44, True, NAVY)
                    text(slide, x, body_y + Inches(1), w, Inches(0.4), "items", 12, color=MUTED)
                elif t["kind"] == "chart" and t["rows"]:
                    chart_data = CategoryChartData()
                    chart_data.categories = [r[0] for r in t["rows"]]
                    chart_data.add_series("Items", [r[1] for r in t["rows"]])
                    kind = XL_CHART_TYPE.DOUGHNUT if t["chart"] == "doughnut" else XL_CHART_TYPE.BAR_CLUSTERED
                    chart = slide.shapes.add_chart(kind, x, body_y, w, body_h, chart_data).chart
                    chart.has_legend = t["chart"] == "doughnut"
                    if chart.has_legend:
                        chart.legend.position, chart.legend.include_in_layout = XL_LEGEND_POSITION.RIGHT, False
                    chart.font.size = Pt(9)
                    plot = chart.plots[0]
                    if kind == XL_CHART_TYPE.BAR_CLUSTERED:
                        plot.vary_by_categories = True
                    for point, color in zip(plot.series[0].points, t["colors"]):
                        point.format.fill.solid()
                        point.format.fill.fore_color.rgb = RGBColor.from_string(_hex(color, "94A3B8"))
                elif t["rows"]:
                    text(slide, x, body_y, w, Inches(0.3), t["summary"], 10, color=MUTED)
                    shown = t["rows"][:8]
                    shape = slide.shapes.add_table(len(shown) + 1, len(t["headers"]), x, body_y + Inches(0.35), w,
                                                   Inches(0.25) * (len(shown) + 1))
                    table = shape.table
                    for c, header in enumerate(t["headers"]):
                        table.cell(0, c).text = header
                    for r, row in enumerate(shown, 1):
                        for c, value in enumerate(row):
                            table.cell(r, c).text = str(value)
                    for cell in (table.cell(r, c) for r in range(len(shown) + 1) for c in range(len(t["headers"]))):
                        for p in cell.text_frame.paragraphs:
                            for run in p.runs:
                                run.font.size = Pt(8)
                    table.columns[0].width = int(w * 0.45) if len(t["headers"]) > 2 else int(w * 0.7)
                    rest = (w - table.columns[0].width) // max(len(t["headers"]) - 1, 1)
                    for c in range(1, len(t["headers"])):
                        table.columns[c].width = rest
                else:
                    text(slide, x, body_y, w, Inches(0.6), t["summary"] or "Nothing matches.", 11, color=MUTED)
    buf = BytesIO()
    deck.save(buf)
    return buf.getvalue()


# ---------------------------------------------------------------------- PDF
def to_pdf(actor, pack) -> bytes:
    from reportlab.graphics.shapes import Drawing, Rect
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    labels = Labels(actor.tenant_id)
    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=styles["Heading1"], textColor=colors.HexColor(f"#{NAVY}"))
    h3 = ParagraphStyle("h3", parent=styles["Heading3"], spaceBefore=8, spaceAfter=2)
    muted = ParagraphStyle("muted", parent=styles["Normal"], textColor=colors.HexColor(f"#{MUTED}"), fontSize=9)
    big = ParagraphStyle("big", parent=styles["Normal"], fontSize=28, leading=32, textColor=colors.HexColor(f"#{NAVY}"))
    cell = ParagraphStyle("cell", parent=styles["Normal"], fontSize=8, leading=10)
    hdr = ParagraphStyle("hdr", parent=cell, textColor=colors.white)
    notes_style = ParagraphStyle("notes", parent=styles["Normal"], fontSize=9, backColor=colors.HexColor("#F5F7FA"),
                                 borderPadding=6, leading=12, spaceBefore=8)
    p = lambda value, style=cell: Paragraph(escape(str(value)), style)  # noqa: E731

    def bar(value, top, color):
        d = Drawing(60 * mm, 4 * mm)
        d.add(Rect(0, 0, 60 * mm * (value / top if top else 0), 3.5 * mm, fillColor=colors.HexColor(f"#{_hex(color, '94A3B8')}"),
                   strokeColor=None))
        return d

    story = [Paragraph(escape(pack["presentation"]["name"]), styles["Title"]), p(_source(pack), muted)]
    if pack["presentation"].get("description"):
        story.append(p(pack["presentation"]["description"], styles["Normal"]))
    for page, tables, error in _pages(pack, labels):
        story += [PageBreak(), Paragraph(escape(page["title"]), h1), p(_source(pack), muted), Spacer(1, 4 * mm)]
        if error:
            story.append(p(error, styles["Normal"]))
        kpis = []

        def flush_kpis():
            # Consecutive number tiles share one row, as on the dashboard.
            if kpis:
                row = Table([[Paragraph(escape(t["title"]), h3) for t in kpis], [Paragraph(str(t["value"]), big) for t in kpis],
                             [p("items", muted) for _ in kpis]], hAlign="LEFT", colWidths=[60 * mm] * len(kpis))
                row.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
                story.append(row)
                kpis.clear()

        for t in tables:
            if t["kind"] == "kpi":
                kpis.append(t)
                if len(kpis) == 4:
                    flush_kpis()
                continue
            flush_kpis()
            block = [Paragraph(escape(t["title"]), h3)]
            block.append(p(t["summary"], muted))
            if t["rows"]:
                rows = t["rows"][:MAX_ROWS]
                if t["kind"] == "chart":
                    top = max((r[1] for r in rows), default=0)
                    data = [[p(h, hdr) for h in t["headers"]] + [""]] + [
                        [p(r[0]), p(r[1]), bar(r[1], top, c)] for r, c in zip(rows, t["colors"])]
                else:
                    data = [[p(h, hdr) for h in t["headers"]]] + [[p(v) for v in r] for r in rows]
                table = Table(data, hAlign="LEFT", repeatRows=1)
                table.setStyle(TableStyle([
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(f"#{NAVY}")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.HexColor(f"#{BORDER}")),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ]))
                block.append(table)
                if len(t["rows"]) > MAX_ROWS:
                    block.append(p(f"… and {len(t['rows']) - MAX_ROWS} more", muted))
            story.append(KeepTogether(block))
        flush_kpis()
        if page.get("notes"):
            story += [Spacer(1, 6 * mm), Paragraph("<b>Notes</b>", styles["Normal"]),
                      Paragraph(escape(page["notes"]).replace("\n", "<br/>"), notes_style)]
    buf = BytesIO()
    SimpleDocTemplate(buf, pagesize=landscape(A4), title=pack["presentation"]["name"],
                      leftMargin=15 * mm, rightMargin=15 * mm, topMargin=12 * mm, bottomMargin=12 * mm).build(story)
    return buf.getvalue()


# ---------------------------------------------------------------------- Excel
def to_xlsx(actor, pack) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font

    labels = Labels(actor.tenant_id)
    wb = Workbook()
    wb.remove(wb.active)
    used = set()
    for page, tables, error in _pages(pack, labels):
        name = re.sub(r"[\[\]:*?/\\]", " ", page["title"])[:28].strip() or "Page"
        base, n = name, 2
        while name.lower() in used:
            name, n = f"{base[:25]} {n}", n + 1
        used.add(name.lower())
        ws = wb.create_sheet(name)
        safe_append(ws, [page["title"]])
        ws["A1"].font = Font(bold=True, size=14)
        safe_append(ws, [_source(pack)])
        if page.get("notes"):
            safe_append(ws, [f"Notes: {page['notes']}"])
            ws.cell(ws.max_row, 1).alignment = Alignment(wrap_text=True)
        if error:
            safe_append(ws, [error])
        for t in tables:
            ws.append([])
            safe_append(ws, [t["title"]])
            ws.cell(ws.max_row, 1).font = Font(bold=True, size=12)
            if t["kind"] == "kpi":
                safe_append(ws, ["Items", t["value"]])
                continue
            safe_append(ws, [t["summary"]])
            if t["rows"]:
                safe_append(ws, t["headers"], header=True)
                for r in t["rows"]:
                    safe_append(ws, r)
        ws.column_dimensions["A"].width = 50
        for col in "BCDE":
            ws.column_dimensions[col].width = 16
    if not wb.sheetnames:
        wb.create_sheet("Pages")
    about_sheet(wb, actor, [("Presentation", pack["presentation"]["name"]), ("Source", _source(pack))])
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()
