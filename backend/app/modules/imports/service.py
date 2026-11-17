"""Import batches: preview a file, then commit or discard it.

Preview and commit run the same code (`_run`): inside one transaction every row is applied through
its service in a savepoint; a row that fails is rolled back to its savepoint and reported, the rest
carry on. A preview then rolls the whole transaction back, so nothing is saved; a commit keeps it,
together with the batch's status, in the same transaction. Committed rows are audited by their
services with source "import" and the batch's correlation ID, so one file's changes can be listed
together in the audit log.

Who: `imports.run`, plus whatever each row needs (people.manage for people, rights on the item for
work…), because each row runs as the person importing it.
"""
import base64
import binascii
import uuid
from io import BytesIO

from sqlalchemy.exc import IntegrityError

from app.core.command import CommandService
from app.core.errors import AppError, Conflict, Forbidden, ValidationFailed
from app.core.models import utcnow
from app.core.pagination import paginate
from app.extensions import db
from app.modules.imports import entities as E
from app.modules.imports.models import MAX_FILE_BYTES, ImportBatch
from app.modules.imports.parsing import FileError, normalise, read_rows
from app.modules.work.service import person_ref

MODES = ("add", "update")


class _DryRun(Exception):
    """Raised at the end of a preview so the transaction rolls everything back."""


class ImportService(CommandService):
    model = ImportBatch
    entity_type = "import_batch"
    permissions = {"create": "imports.run", "update": "imports.run", "delete": "imports.run"}

    def base_query(self):
        stmt = super().base_query()
        if self.actor is None or self.actor.is_admin:
            return stmt
        return stmt.where(ImportBatch.owner_id == self.actor.id)

    def audit_value(self, field, value):
        if field == "content":
            return f"{len(value or b'')} bytes"
        if field == "results":
            return f"{len(value or [])} rows"
        return value

    # ------------------------------------------------------------------ the run
    def _headers(self, entity, headers):
        """{file header: column key or "cf:<normalised>"}, the unknown headers, and missing required ones."""
        custom = E.custom_columns(entity, self.tenant_id)
        by_name = {}
        for c in entity.columns:
            by_name[normalise(c.label)] = c.key
            by_name.setdefault(normalise(c.key), c.key)
        mapping, unknown = {}, []
        for h in headers:
            n = normalise(h)
            if not n:
                continue
            if n in by_name:
                mapping[h] = by_name[n]
            elif n in custom:
                mapping[h] = f"cf:{n}"
            else:
                unknown.append(h)
        present = set(mapping.values())
        missing = [c.label for c in entity.columns if c.required and c.key not in present]
        return mapping, unknown, missing, custom

    def _run(self, entity_code, mode, filename, content, correlation_id, *, commit=False, on_commit=None):
        entity = E.ENTITIES[entity_code]
        try:
            headers, rows = read_rows(content, filename, sheet=entity.label)
        except FileError as exc:
            raise ValidationFailed(str(exc), {"field": "file"}) from exc
        mapping, unknown, missing, custom = self._headers(entity, headers)
        if missing:
            raise ValidationFailed(f"The file has no column for: {', '.join(missing)}. Start from the template.",
                                   {"field": "file"})
        ctx = E.Context(self.actor, self.tenant_id, correlation_id=correlation_id, mode=mode, filename=filename)
        prepared = [(n, {mapping[h]: v for h, v in raw.items() if h in mapping}) for n, raw in rows]
        results = []
        try:
            with self.transaction():
                for n, values in E.order_rows(entity, prepared):
                    results.append(self._row(ctx, entity, n, values, custom))
                results.sort(key=lambda r: r["row"])
                summary = self._summary(results, unknown)
                if not commit:
                    raise _DryRun
                on_commit(summary, results)
        except _DryRun:
            pass
        return summary, results

    def _row(self, ctx, entity, n, values, custom):
        key = E.identity_of(entity, values)
        if E.is_example(entity, values):
            return {"row": n, "key": key, "action": "skipped", "errors": [], "note": "Example row"}
        point = db.session.begin_nested()
        try:
            outcome = E.apply_row(ctx, entity, values, custom)
            point.commit()
            return {"row": n, "key": key, "errors": [], **outcome}
        except E.RowInvalid as exc:
            point.rollback()
            return {"row": n, "key": key, "action": "invalid", "errors": exc.errors}
        except AppError as exc:
            point.rollback()
            return {"row": n, "key": key, "action": "invalid", "errors": [{"column": self._column(entity, exc), "message": exc.message}]}
        except IntegrityError:
            point.rollback()
            return {"row": n, "key": key, "action": "invalid",
                    "errors": [{"column": None, "message": "Conflicts with an existing record (duplicate or missing link)"}]}

    @staticmethod
    def _column(entity, exc):
        details = exc.details if isinstance(exc.details, dict) else {}
        fieldname = details.get("field")
        col = next((c for c in entity.columns if c.field and c.field == fieldname), None)
        return col.label if col else None

    @staticmethod
    def _summary(results, unknown):
        count = lambda a: sum(1 for r in results if r["action"] == a)  # noqa: E731
        return {"rows": len(results), "create": count("create"), "update": count("update"),
                "unchanged": count("unchanged"), "invalid": count("invalid"), "skipped": count("skipped"),
                "ignored_columns": unknown}

    # ------------------------------------------------------------------ commands
    def preview(self, entity, mode, filename, content_b64):
        if entity not in E.ENTITIES:
            raise ValidationFailed("Choose what to import", {"field": "entity"})
        if mode not in MODES:
            raise ValidationFailed("Choose add-only or add and update", {"field": "mode"})
        try:
            content = base64.b64decode(content_b64 or "", validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValidationFailed("The file could not be read", {"field": "file"}) from exc
        if not content:
            raise ValidationFailed("The file is empty", {"field": "file"})
        if len(content) > MAX_FILE_BYTES:
            raise ValidationFailed(f"Files can be up to {MAX_FILE_BYTES // (1024 * 1024)} MB", {"field": "file"})
        filename = (filename or "import.xlsx").replace("\\", "/").split("/")[-1][:255]
        correlation_id = uuid.uuid4().hex
        summary, results = self._run(entity, mode, filename, content, correlation_id)
        return self.create({"entity": entity, "mode": mode, "filename": filename, "content": content,
                            "status": "previewed", "owner_id": getattr(self.actor, "id", None),
                            "correlation_id": correlation_id, "summary": summary, "results": results},
                           reason=f"Previewed {filename}")

    def commit(self, batch_id):
        batch = self.get(batch_id)
        if batch.owner_id != getattr(self.actor, "id", None):
            raise Forbidden("Only the person who uploaded the file can import it")
        if batch.status != "previewed":
            raise Conflict(f"This file was already {batch.status}")

        def finish(summary, results):
            self.update(batch.id, {"status": "committed", "summary": summary, "results": results,
                                   "committed_at": utcnow()}, reason=f"Imported {batch.filename}")

        self._run(batch.entity, batch.mode, batch.filename, batch.content, batch.correlation_id,
                  commit=True, on_commit=finish)
        return self.get(batch.id)

    def discard(self, batch_id):
        batch = self.get(batch_id)
        if batch.status != "previewed":
            raise Conflict(f"This file was already {batch.status}")
        return self.update(batch.id, {"status": "discarded"}, reason="Discarded after preview")

    # ------------------------------------------------------------------ reads
    def list(self, params):
        stmt = self.base_query().order_by(ImportBatch.created_at.desc(), ImportBatch.id.desc())
        return paginate(stmt, params, lambda b: self.serialize(b, brief=True))

    def serialize(self, b, brief=False):
        from app.modules.auth.models import User

        out = {"id": b.id, "entity": b.entity, "entity_label": E.ENTITIES[b.entity].label, "mode": b.mode,
               "filename": b.filename, "status": b.status, "summary": b.summary or {},
               "owner": person_ref(db.session.get(User, b.owner_id)), "correlation_id": b.correlation_id,
               "created_at": b.created_at.isoformat(), "committed_at": b.committed_at.isoformat() if b.committed_at else None,
               "can_commit": b.status == "previewed" and b.owner_id == getattr(self.actor, "id", None)}
        if not brief:
            out["results"] = b.results or []
        return out


# ---------------------------------------------------------------------- templates
def entity_catalog(tenant_id) -> list[dict]:
    out = []
    for e in E.ENTITIES.values():
        custom = [f["label"] for f in {id(f): f for f in E.custom_columns(e, tenant_id).values()}.values()]
        out.append({"code": e.code, "label": e.label, "identity": e.identity, "order_note": e.order_note,
                    "columns": [{"key": c.key, "label": c.label, "required": c.required, "help": c.help} for c in e.columns],
                    "custom_columns": custom})
    return out


def template_xlsx(tenant_id, entity_code) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font

    from app.modules.config.versioning import published_list
    from app.modules.snapshots.exports import safe_append

    entity = E.ENTITIES.get(entity_code)
    if entity is None:
        raise ValidationFailed("Unknown template")
    custom = list({id(f): f for f in E.custom_columns(entity, tenant_id).values()}.values())
    wb = Workbook()
    ws = wb.active
    ws.title = entity.label
    safe_append(ws, [c.label for c in entity.columns] + [f["label"] for f in custom], header=True)
    for example in entity.examples:
        safe_append(ws, [example.get(c.key) for c in entity.columns] + [None for _ in custom])
    for i, _ in enumerate(entity.columns + custom, 1):
        ws.column_dimensions[ws.cell(1, i).column_letter].width = 20
    ws.freeze_panes = "A2"

    info = wb.create_sheet("Instructions")
    for line in [f"How to fill in: {entity.label}",
                 "Fill in the first sheet, one row per record. Keep the column names. Rows whose ID starts with "
                 "EXAMPLE are samples and are skipped.",
                 f"Each row is identified by: {entity.identity}. “Add only” rejects rows that already exist; "
                 "“Add and update” updates them with the cells you fill in (empty cells leave values as they are).",
                 "Dates: 2026-12-31, 31/12/2026 (day first), 31-Dec-2026 or an Excel date. People: their email.",
                 entity.order_note, ""]:
        if line is not None:
            info.append([line])
    info["A1"].font = Font(bold=True, size=13)
    safe_append(info, ["Column", "Required", "What to enter", "Allowed values"], header=True)
    for c in entity.columns:
        allowed = ""
        if c.lookup:
            allowed = ", ".join(v["label"] for v in published_list(tenant_id, c.lookup).values() if v["is_active"])
        safe_append(info, [c.label, "Yes" if c.required else "", c.help, allowed])
    for f in custom:
        safe_append(info, [f["label"], "Yes" if f["is_required"] else "", f.get("help_text") or "Custom field", ""])
    for col, width in zip("ABCD", (24, 10, 70, 50)):
        info.column_dimensions[col].width = width
    for row in info.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical="top")
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()
