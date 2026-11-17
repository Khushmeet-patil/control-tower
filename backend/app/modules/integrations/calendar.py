"""Personal calendar feed (.ics) for Outlook, Google Calendar or Apple Calendar.

    GET /api/v1/calendar/feed.ics?token=ct_…

Outlook: Add calendar → Subscribe from web → paste the address. Calendar apps cannot send headers, so the
token travels in the address; make it with "calendar" scope only (My account → Calendar feed), which
opens nothing but this feed. The feed holds, for the token's owner:
- open work they are accountable for, responsible for or assigned to that has a planned finish
  (an all-day event on that date; milestones are marked as such);
- their time off.
"""
from datetime import timedelta

from sqlalchemy import or_, select

from app.core.dates import today
from app.core.models import utcnow
from app.extensions import db
from app.modules.config.versioning import published_list

HORIZON_PAST_DAYS = 90


def _escape(text: str) -> str:
    return (text or "").replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\r", "").replace("\n", "\\n")


def _fold(line: str) -> list[str]:
    """iCalendar lines are at most 75 octets; longer ones continue on lines starting with a space."""
    out, raw = [], line.encode("utf-8")
    while len(raw) > 75:
        cut = 75
        while cut > 0 and (raw[cut] & 0xC0) == 0x80:  # never split a UTF-8 character
            cut -= 1
        out.append(raw[:cut].decode("utf-8"))
        raw = b" " + raw[cut:]
    out.append(raw.decode("utf-8"))
    return out


def _event(uid, day, end_day, summary, description, url=None):
    stamp = utcnow().strftime("%Y%m%dT%H%M%SZ")
    lines = ["BEGIN:VEVENT", f"UID:{uid}", f"DTSTAMP:{stamp}", f"DTSTART;VALUE=DATE:{day:%Y%m%d}",
             f"DTEND;VALUE=DATE:{end_day:%Y%m%d}", f"SUMMARY:{_escape(summary)}",
             f"DESCRIPTION:{_escape(description)}", "TRANSP:TRANSPARENT"]
    if url:
        lines.append(f"URL:{url}")
    lines.append("END:VEVENT")
    return lines


def feed(user) -> str:
    from app.modules.capacity.models import TimeOff
    from app.modules.notifications.service import app_url
    from app.modules.work.models import WorkItem
    from app.modules.work.service import closed_status_ids, involved_item_ids

    tid = user.tenant_id
    since = today() - timedelta(days=HORIZON_PAST_DAYS)
    closed = closed_status_ids(tid)
    stmt = select(WorkItem).where(WorkItem.tenant_id == tid, WorkItem.is_deleted.is_(False),
                                  WorkItem.planned_end.is_not(None), WorkItem.planned_end >= since,
                                  or_(*(WorkItem.id.in_(s) for s in involved_item_ids(user.id))))
    if closed:
        stmt = stmt.where(or_(WorkItem.status_id.is_(None), WorkItem.status_id.not_in(closed)))
    types = published_list(tid, "item_type")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Control Tower//Work calendar//EN", "CALSCALE:GREGORIAN",
             "METHOD:PUBLISH", f"X-WR-CALNAME:{_escape('Control Tower · ' + user.full_name)}",
             "X-PUBLISHED-TTL:PT1H", "REFRESH-INTERVAL;VALUE=DURATION:PT1H"]
    for w in db.session.scalars(stmt.order_by(WorkItem.planned_end)):
        kind = (types.get(w.item_type_id) or {}).get("label") or "Item"
        role = "Accountable" if w.accountable_id == user.id else "Working on it"
        lines += _event(f"work-{w.id}@control-tower", w.planned_end, w.planned_end + timedelta(days=1),
                        f"Due: {w.code} {w.title}", f"{kind} · {role}. Planned finish {w.planned_end.isoformat()}.",
                        app_url(f"/pages/item.html?id={w.id}"))
    offs = db.session.scalars(select(TimeOff).where(TimeOff.tenant_id == tid, TimeOff.is_deleted.is_(False),
                                                    TimeOff.person_id == user.id, TimeOff.end_date >= since))
    kinds = published_list(tid, "time_off_type")
    for t in offs:
        label = (kinds.get(t.kind_id) or {}).get("label") or "Time off"
        lines += _event(f"timeoff-{t.id}@control-tower", t.start_date, t.end_date + timedelta(days=1),
                        f"{label}", t.note or label)
    lines.append("END:VCALENDAR")
    return "\r\n".join(part for line in lines for part in _fold(line)) + "\r\n"
