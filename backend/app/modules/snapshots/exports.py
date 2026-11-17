"""Excel exports of work lists: live (the Portfolio with its filters) or from a snapshot.

Both use the viewer's scope and the same filters as the screen, so the file matches the list on
screen. Lookup ids are written as their labels.
"""
from datetime import date
from io import BytesIO

from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from app.core.models import utcnow
from app.modules.config.versioning import published_list, published_snapshot
from app.modules.snapshots import frozen
from app.modules.work.service import WorkItemService, portfolio_params

HEADER_FILL = PatternFill("solid", fgColor="2F5D8A")
HEADER_FONT = Font(bold=True, color="FFFFFF")
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
COLUMNS = [  # header, key, width
    ("Code", "code", 12), ("Title", "title", 44), ("Type", "item_type_id", 14), ("Status", "status_id", 14),
    ("Priority", "priority_id", 12), ("Health", "health", 10), ("Health reason", "health_reason", 40),
    ("Progress %", "progress", 11), ("Unit", "unit", 22), ("Accountable", "accountable", 22),
    ("Planned start", "planned_start", 13), ("Planned finish", "planned_end", 13), ("Actual finish", "actual_end", 13),
    ("Overdue", "is_overdue", 9),
]


class Labels:
    """Published lookup labels and colours by id; health labels by code."""

    def __init__(self, tenant_id):
        values = published_snapshot(tenant_id)[0].get("lookup_values", [])
        self.by_id = {v["id"]: v for v in values}
        self.health = {v["code"]: v for v in published_list(tenant_id, "health").values()}

    def label(self, value_id):
        v = self.by_id.get(value_id)
        return v["label"] if v else None

    def color(self, value_id):
        v = self.by_id.get(value_id)
        return v.get("color") if v else None

    def health_label(self, code):
        if not code or code == "na":
            return "Not assessed"
        return (self.health.get(code) or {}).get("label") or code.capitalize()

    def health_color(self, code):
        return (self.health.get(code) or {}).get("color")

    def group(self, group_by, g) -> tuple[str, str | None]:
        """A chart group's label and colour (as groupDisplay() in dashboard-widget.js)."""
        value = g.get("value")
        if value is None:
            return "Not set", None
        if group_by == "health":
            return self.health_label(value), self.health_color(value)
        if group_by == "accountable_id":
            return (g.get("person") or {}).get("full_name") or f"Person {value}", None
        try:
            return self.label(int(value)) or str(value), self.color(int(value))
        except (TypeError, ValueError):
            return str(value), None


def live_rows(actor, filters) -> list[dict]:
    """The Portfolio list for these filters, as rows with the snapshot row shape."""
    from app.modules.rules import engine
    from app.modules.work.progress import progress_map

    work = WorkItemService(actor)
    items = work.rows(portfolio_params(filters))
    ids = [w.id for w in items]
    progress = progress_map(actor.tenant_id, ids)
    health = engine.evaluate(actor.tenant_id, ids)
    out = []
    for w in items:
        r = health.get(w.id)
        out.append({"code": w.code, "title": w.title, "item_type_id": w.item_type_id, "status_id": w.status_id,
                    "priority_id": w.priority_id, "health": {"code": r.health if r else None,
                                                            "reason": (r.top.reason if r and r.top else None)},
                    "progress": progress.get(w.id, 0), "unit": {"name": w.unit.name} if w.unit else None,
                    "accountable": {"full_name": w.accountable.full_name} if w.accountable else None,
                    "planned_start": w.planned_start, "planned_end": w.planned_end, "actual_end": w.actual_end,
                    "is_overdue": work.is_overdue(w)})
    return out


def _cell(row, key, labels):
    v = row.get(key)
    if key in ("item_type_id", "status_id", "priority_id"):
        return labels.label(v)
    if key == "health":
        return labels.health_label((v or {}).get("code"))
    if key == "health_reason":
        return (row.get("health") or {}).get("reason")
    if key in ("unit", "accountable"):
        return (v or {}).get("name") or (v or {}).get("full_name")
    if key in ("planned_start", "planned_end", "actual_end") and isinstance(v, str):
        return date.fromisoformat(v)
    if key == "is_overdue":
        return "Yes" if v else ""
    return v


FORMULA_START = ("=", "+", "-", "@")


def xcell(ws, value, number_format=None, bold=False, header=False):
    """A cell for any worksheet (streaming or normal). Text that looks like a formula stays text, so a
    title such as "=HYPERLINK(…)" can never run as a formula in someone's spreadsheet."""
    cell = WriteOnlyCell(ws, value=value)
    if isinstance(value, str) and value.startswith(FORMULA_START):
        cell.data_type = "s"
    if number_format:
        cell.number_format = number_format
    if header:
        cell.fill, cell.font, cell.alignment = HEADER_FILL, HEADER_FONT, Alignment(vertical="center")
    elif bold:
        cell.font = Font(bold=True)
    return cell


def safe_append(ws, values, **kw):
    ws.append([xcell(ws, v, **kw) for v in values])


def style_header(ws, row=1):
    for cell in ws[row]:
        cell.fill, cell.font = HEADER_FILL, HEADER_FONT
        cell.alignment = Alignment(vertical="center")


DATE_KEYS = ("planned_start", "planned_end", "actual_end")


def write_rows(ws, rows, labels):
    """The work table, streamed (write-only worksheets keep large exports fast and small in memory)."""
    for i, (_, _, width) in enumerate(COLUMNS, 1):
        ws.column_dimensions[get_column_letter(i)].width = width
    ws.freeze_panes = "C2"
    safe_append(ws, [h for h, _, _ in COLUMNS], header=True)
    n = 0
    for row in rows:
        ws.append([xcell(ws, _cell(row, key, labels), "dd mmm yyyy" if key in DATE_KEYS else None) for _, key, _ in COLUMNS])
        n += 1
    ws.auto_filter.ref = f"A1:{get_column_letter(len(COLUMNS))}{n + 1}"


def about_sheet(wb, actor, lines):
    ws = wb.create_sheet("About")
    ws.column_dimensions["A"].width, ws.column_dimensions["B"].width = 22, 70
    for k, v in [("Exported by", getattr(actor, "full_name", "System")), ("Exported at (UTC)", utcnow()), *lines]:
        ws.append([xcell(ws, k, bold=True), xcell(ws, v)])


def _save(wb) -> bytes:
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def work_table(actor, filters) -> list[dict]:
    """The live list as plain rows ({column header: value}), for CSV and JSON."""
    labels = Labels(actor.tenant_id)
    out = []
    for row in live_rows(actor, filters):
        values = {}
        for header, key, _ in COLUMNS:
            v = _cell(row, key, labels)
            values[header] = v.isoformat() if isinstance(v, date) else v
        out.append(values)
    return out


def work_csv(actor, filters) -> bytes:
    import csv
    import io

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([h for h, _, _ in COLUMNS])
    for row in work_table(actor, filters):
        writer.writerow(["" if v is None else _safe_csv(v) for v in row.values()])
    return ("\ufeff" + buf.getvalue()).encode("utf-8")  # BOM, so Excel opens it as UTF-8


def _safe_csv(value):
    """Stop spreadsheet formula injection: text starting with = + - @ is written as text."""
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + value
    return value


def work_xlsx(actor, filters) -> bytes:
    labels = Labels(actor.tenant_id)
    wb = Workbook(write_only=True)
    ws = wb.create_sheet("Work")
    write_rows(ws, live_rows(actor, filters), labels)
    about_sheet(wb, actor, [("Source", "Live data"), ("Filters", _describe(filters))])
    return _save(wb)


def snapshot_xlsx(actor, snapshot, filters) -> bytes:
    labels = Labels(actor.tenant_id)
    rows = [frozen.row_out(r) for r in frozen.FrozenSet(actor, snapshot).select(portfolio_params(filters))]
    wb = Workbook(write_only=True)
    ws = wb.create_sheet("Work")
    write_rows(ws, rows, labels)
    about_sheet(wb, actor, [("Source", f"Snapshot “{snapshot.label}” as of {snapshot.as_of:%d %b %Y} ({snapshot.status})"),
                            ("Filters", _describe(filters))])
    return _save(wb)


def _describe(filters):
    return ", ".join(f"{k}={v}" for k, v in (filters or {}).items() if v not in (None, "")) or "None (top-level work)"
