"""Capacity engine: how much each person can take on, today and week by week.

    available %  = capacity_pct (share of a full week they work) × working days not on time off ÷ working days
    usable %     = available % × (100 − buffer) ÷ 100     (buffer = capacity kept for unplanned work)
    load %       = sum of allocation % of assignments covering the day / overlapping the week, on open work
    free %       = max(0, usable − load)
    status       = on_leave (no availability) · overloaded (load > usable) · underutilised (load < usable ÷ 2) · balanced

The buffer is the published "owner overloaded" health rule's setting (rules.engine.capacity_buffer), so the
team view, the Action Centre and the health rules all agree. Working days are each person's own
(User.work_days, Monday to Friday unless set), less the public holidays of their unit and the units above it.
Everything is calculated on read; nothing is stored.
"""
from datetime import date, timedelta

from sqlalchemy import func, or_, select

from app.core.dates import today
from app.extensions import db
from app.modules.auth.models import User
from app.modules.capacity.models import PublicHoliday, TimeOff
from app.modules.work.models import Assignment, WorkItem
from app.modules.work.service import closed_status_ids


DEFAULT_WORK_DAYS = (0, 1, 2, 3, 4)


def working_days(start: date, end: date, weekdays=DEFAULT_WORK_DAYS) -> list[date]:
    days, d = [], start
    while d <= end:
        if d.weekday() in weekdays:
            days.append(d)
        d += timedelta(days=1)
    return days


def holidays_for(tenant_id, person_ids, start: date, end: date) -> dict[int, set[date]]:
    """Public holidays between start and end that apply to each person (their unit or a unit above it)."""
    from app.core.tree import ancestor_ids
    from app.modules.organisation.models import OrgUnitClosure

    out = {int(p): set() for p in person_ids}
    rows = db.session.execute(select(PublicHoliday.holiday_date, PublicHoliday.unit_id).where(
        PublicHoliday.tenant_id == tenant_id, PublicHoliday.is_deleted.is_(False),
        PublicHoliday.holiday_date >= start, PublicHoliday.holiday_date <= end)).all()
    if not rows or not out:
        return out
    units = dict(db.session.execute(select(User.id, User.unit_id).where(User.id.in_(list(out)))).all())
    chains = {}
    for pid in out:
        unit = units.get(pid)
        if unit not in chains:
            chains[unit] = set(ancestor_ids(OrgUnitClosure, unit, include_self=True)) if unit else set()
        for day, unit_id in rows:
            if unit_id is None or unit_id in chains[unit]:
                out[pid].add(day)
    return out


def person_workdays(tenant_id, person_ids, start: date, end: date) -> dict[int, list[date]]:
    """Each person's working days between start and end: their weekdays, less public holidays."""
    ids = [int(p) for p in person_ids]
    if not ids:
        return {}
    weekdays = dict(db.session.execute(select(User.id, User.work_days).where(User.id.in_(ids))).all())
    holidays = holidays_for(tenant_id, ids, start, end)
    return {p: [d for d in working_days(start, end, tuple(weekdays.get(p) or DEFAULT_WORK_DAYS)) if d not in holidays[p]]
            for p in ids}


def week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())


def load_status(load: int, usable: int, available: int = 100) -> str:
    """The prototype's capacity bands, plus "on leave" when the person is not available at all."""
    if available <= 0:
        return "on_leave"
    if load > usable:
        return "overloaded"
    if load < usable / 2:
        return "underutilised"
    return "balanced"


def capacity_pct(person_ids) -> dict[int, int]:
    ids = list({int(p) for p in person_ids})
    if not ids:
        return {}
    found = dict(db.session.execute(select(User.id, User.capacity_pct).where(User.id.in_(ids))).all())
    return {p: (100 if found.get(p) is None else found[p]) for p in ids}


def days_off(tenant_id, person_ids, start: date, end: date, workdays: dict | None = None) -> dict[int, set[date]]:
    """Working days each person is off between start and end (inclusive). `workdays` = person_workdays()."""
    out = {int(p): set() for p in person_ids}
    if not out:
        return out
    rows = db.session.execute(select(TimeOff.person_id, TimeOff.start_date, TimeOff.end_date).where(
        TimeOff.tenant_id == tenant_id, TimeOff.is_deleted.is_(False), TimeOff.person_id.in_(list(out)),
        TimeOff.start_date <= end, TimeOff.end_date >= start)).all()
    for pid, s, e in rows:
        days = workdays.get(pid, []) if workdays is not None else working_days(max(s, start), min(e, end))
        span = {d for d in days if max(s, start) <= d <= min(e, end)}
        out[pid] |= span
    return out


def load_between(tenant_id, person_ids, start: date, end: date) -> dict[int, dict]:
    """{person: {"pct", "items"}}: assignments overlapping [start, end] on live, open work."""
    ids = [int(p) for p in person_ids]
    if not ids:
        return {}
    closed = closed_status_ids(tenant_id)
    stmt = (select(Assignment.person_id, func.coalesce(func.sum(Assignment.allocation_pct), 0), func.count(Assignment.id))
            .join(WorkItem, WorkItem.id == Assignment.work_item_id)
            .where(Assignment.tenant_id == tenant_id, Assignment.is_deleted.is_(False), WorkItem.is_deleted.is_(False),
                   Assignment.person_id.in_(ids),
                   or_(Assignment.start_date.is_(None), Assignment.start_date <= end),
                   or_(Assignment.end_date.is_(None), Assignment.end_date >= start))
            .group_by(Assignment.person_id))
    if closed:
        stmt = stmt.where(or_(WorkItem.status_id.is_(None), WorkItem.status_id.not_in(closed)))
    found = {pid: {"pct": int(pct), "items": n} for pid, pct, n in db.session.execute(stmt)}
    return {pid: found.get(pid, {"pct": 0, "items": 0}) for pid in ids}


def _figures(load, cap, workdays, off, buffer, normal_days=None):
    """`workdays`: the person's working days in the period (after holidays); `normal_days`: how many working
    days a normal period of theirs has (holidays reduce availability, as time off does)."""
    normal = normal_days if normal_days is not None else len(workdays)
    available = round(cap * (len(workdays) - len(off)) / normal) if normal else 0
    usable = round(available * (100 - buffer) / 100)
    return {"load_pct": load, "capacity_pct": cap, "available_pct": available, "usable_pct": usable,
            "free_pct": max(0, usable - load), "status": load_status(load, usable, available)}


def people_now(tenant_id, person_ids, buffer: int) -> dict[int, dict]:
    """Today's figures per person (what the Team view, the Action Centre and the rules use)."""
    from app.modules.work.service import allocation_load

    ids = [int(p) for p in person_ids]
    day = today()
    caps, loads = capacity_pct(ids), allocation_load(tenant_id, ids, day)
    # Today's availability: a day off or a public holiday counts as on leave; a person's non-working
    # day (e.g. a weekend) counts as a normal day.
    weekdays = dict(db.session.execute(select(User.id, User.work_days).where(User.id.in_(ids or [0]))).all())
    holidays = holidays_for(tenant_id, ids, day, day)
    off = days_off(tenant_id, ids, day, day, {p: [day] for p in ids})
    upcoming = next_time_off(tenant_id, ids)
    out = {}
    for p in ids:
        works_today = day.weekday() in tuple(weekdays.get(p) or DEFAULT_WORK_DAYS)
        away = (off[p] | holidays[p]) if works_today else set()
        f = _figures(loads[p]["pct"], caps[p], [day], away, buffer)
        out[p] = {**f, "allocated_items": loads[p]["items"], "next_time_off": upcoming.get(p)}
    return out


def next_time_off(tenant_id, person_ids) -> dict[int, dict]:
    rows = db.session.scalars(select(TimeOff).where(
        TimeOff.tenant_id == tenant_id, TimeOff.is_deleted.is_(False), TimeOff.person_id.in_(list(person_ids) or [0]),
        TimeOff.end_date >= today()).order_by(TimeOff.start_date)).all()
    out = {}
    for r in rows:
        out.setdefault(r.person_id, {"start_date": r.start_date.isoformat(), "end_date": r.end_date.isoformat(),
                                     "kind_id": r.kind_id})
    return out


def weekly(tenant_id, person_ids, buffer: int, weeks: int = 8) -> dict[int, list[dict]]:
    """Week-by-week figures from this week on (time-phased allocation and time off)."""
    ids = [int(p) for p in person_ids]
    caps = capacity_pct(ids)
    first = week_start(today())
    out = {p: [] for p in ids}
    weekdays = dict(db.session.execute(select(User.id, User.work_days).where(User.id.in_(ids or [0]))).all())
    for n in range(weeks):
        start = first + timedelta(weeks=n)
        end = start + timedelta(days=6)
        workdays = person_workdays(tenant_id, ids, start, end)
        loads, off = load_between(tenant_id, ids, start, end), days_off(tenant_id, ids, start, end, workdays)
        for p in ids:
            normal = len(working_days(start, end, tuple(weekdays.get(p) or DEFAULT_WORK_DAYS)))
            out[p].append({"week_start": start.isoformat(),
                           **_figures(loads[p]["pct"], caps[p], workdays[p], off[p], buffer, normal)})
    return out


def rollup(figures: list[dict]) -> dict:
    """Used and free capacity of a group of people (a unit and everything below it)."""
    return {
        "people": len(figures), "usable_pct": sum(f["usable_pct"] for f in figures),
        "load_pct": sum(f["load_pct"] for f in figures), "free_pct": sum(f["free_pct"] for f in figures),
        "overloaded": sum(1 for f in figures if f["status"] == "overloaded"),
        "on_leave": sum(1 for f in figures if f["status"] == "on_leave"),
    }
