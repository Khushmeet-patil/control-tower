"""Reading spreadsheet files and turning cells into values.

read_rows(content, filename, sheet) → (headers, [(row number, {header: value})])
    .xlsx (openpyxl, read-only) or .csv (UTF-8, with or without BOM; comma or semicolon). Fully
    empty rows are skipped. Row numbers are the ones a person sees in Excel.

Cell conversions raise CellError with a message a person can act on:
    parse_date   2026-12-31 · 31/12/2026 (day first) · 31-12-2026 · 31.12.2026 · 31-Dec-2026 ·
                 31 Dec 2026 · Dec 31 2026 · December 31, 2026 · Excel dates and serial numbers
    parse_int    40 · 40% · 40.0
    parse_bool   yes/no · true/false · y/n · 1/0
    split_list   "a, b; c" → ["a", "b", "c"]
"""
import csv
import io
import re
from datetime import date, datetime, timedelta

MAX_ROWS = 5000
EXCEL_EPOCH = date(1899, 12, 30)
DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%d/%m/%y", "%d-%b-%Y", "%d-%b-%y", "%d %b %Y",
                "%d %B %Y", "%b %d %Y", "%B %d %Y", "%b %d, %Y", "%B %d, %Y", "%Y/%m/%d")


class CellError(ValueError):
    pass


class FileError(ValueError):
    pass


def normalise(text) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(text or "").lower())


def _clean(value):
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return value


def read_rows(content: bytes, filename: str, sheet: str | None = None):
    name = (filename or "").lower()
    if name.endswith(".csv"):
        return _read_csv(content)
    if name.endswith(".xlsx") or name.endswith(".xlsm"):
        return _read_xlsx(content, sheet)
    raise FileError("Upload an Excel (.xlsx) or CSV (.csv) file")


def _read_csv(content):
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise FileError("The CSV file must be saved as UTF-8") from exc
    sample = text[:4096]
    delimiter = ";" if sample.count(";") > sample.count(",") else ","
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    rows = list(reader)
    return _table(rows)


def _read_xlsx(content, sheet):
    from openpyxl import load_workbook

    try:
        wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    except Exception as exc:  # noqa: BLE001 — any failure here means the file is not a readable workbook
        raise FileError("This is not a readable Excel file") from exc
    try:
        names = wb.sheetnames
        chosen = next((n for n in names if sheet and normalise(n) == normalise(sheet)), None) \
            or next((n for n in names if "instruction" not in n.lower()), names[0])
        ws = wb[chosen]
        rows = []
        for row in ws.iter_rows(values_only=True):
            rows.append(list(row))
            if len(rows) > MAX_ROWS + 1:
                break
        return _table(rows)
    finally:
        wb.close()


def _table(rows):
    rows = [[_clean(c) for c in r] for r in rows]
    while rows and not any(c is not None for c in rows[0]):
        rows.pop(0)
    if not rows:
        raise FileError("The file is empty")
    headers = [str(h) if h is not None else "" for h in rows[0]]
    out = []
    for n, row in enumerate(rows[1:], start=2):
        if not any(c is not None for c in row):
            continue
        out.append((n, {headers[i]: row[i] for i in range(min(len(headers), len(row))) if headers[i]}))
    if len(out) > MAX_ROWS:
        raise FileError(f"A file can hold up to {MAX_ROWS} rows; split it into smaller files")
    return headers, out


# ---------------------------------------------------------------------- cells
def parse_date(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if 1 <= value < 2958466:  # an Excel serial date
            return EXCEL_EPOCH + timedelta(days=int(value))
        raise CellError(f"{value} is not a date")
    text = re.sub(r"\s+", " ", str(value).strip())
    text = re.sub(r"[T ]\d{1,2}:\d{2}(:\d{2})?$", "", text)  # a time after the date is ignored
    if re.fullmatch(r"\d+(\.0+)?", text):
        return parse_date(float(text))
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise CellError(f"“{value}” is not a date we can read; use 2026-12-31 or 31/12/2026")


def parse_int(value, *, low=None, high=None):
    if value is None:
        return None
    if isinstance(value, bool):
        raise CellError("Enter a number")
    if isinstance(value, (int, float)):
        number = value
    else:
        text = str(value).strip().rstrip("%").replace(",", "").strip()
        try:
            number = float(text)
        except ValueError as exc:
            raise CellError(f"“{value}” is not a number") from exc
    if number != int(number):
        raise CellError(f"{value} must be a whole number")
    number = int(number)
    if (low is not None and number < low) or (high is not None and number > high):
        raise CellError(f"{number} must be between {low} and {high}")
    return number


def parse_bool(value):
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in ("yes", "y", "true", "1", "active"):
        return True
    if text in ("no", "n", "false", "0", "inactive"):
        return False
    raise CellError(f"“{value}” must be Yes or No")


def split_list(value) -> list[str]:
    if value is None:
        return []
    return [p.strip() for p in re.split(r"[,;\n]", str(value)) if p.strip()]


def text(value, max_len=None):
    if value is None:
        return None
    if isinstance(value, float) and value == int(value):
        value = int(value)  # 1001.0 from Excel → "1001"
    s = value.isoformat() if isinstance(value, (date, datetime)) else str(value).strip()
    if max_len and len(s) > max_len:
        raise CellError(f"Too long: at most {max_len} characters")
    return s or None
