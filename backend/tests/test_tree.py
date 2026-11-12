"""Closure-table helpers shared by both hierarchies."""
from sqlalchemy import select

from app.core.tree import ancestor_ids, descendant_ids, rebuild_closure
from app.extensions import db
from app.modules.organisation.models import OrgUnit, OrgUnitClosure
from tests.conftest import unit_id


def closure_rows():
    return set(db.session.execute(select(OrgUnitClosure.ancestor_id, OrgUnitClosure.descendant_id,
                                         OrgUnitClosure.depth)).all())


def test_descendants_and_ancestors(demo):
    tech = descendant_ids(OrgUnitClosure, [unit_id("TECH")])
    assert {unit_id(c) for c in ("TECH", "ENG", "QUAL", "PLAT", "MOB")} == tech
    assert ancestor_ids(OrgUnitClosure, unit_id("PLAT")) == [unit_id("ORG"), unit_id("TECH"), unit_id("ENG")]


def test_move_keeps_closure_consistent(demo, admin):
    from app.modules.organisation.service import UnitService

    UnitService(admin).update(unit_id("ENG"), {"parent_id": unit_id("OPS")}, reason="Reorganisation")
    assert unit_id("PLAT") in descendant_ids(OrgUnitClosure, [unit_id("OPS")])
    assert unit_id("PLAT") not in descendant_ids(OrgUnitClosure, [unit_id("TECH")])
    before = closure_rows()
    rebuild_closure(OrgUnitClosure, OrgUnit, admin.tenant_id)  # derived data must match a full rebuild
    assert closure_rows() == before
