"""Tests for the entitlement bootstrap catalog/templates (item 5)."""

from __future__ import annotations

from irp_shared.entitlement.bootstrap import (
    ALL_CODES,
    PERMISSIONS,
    ROLE_TEMPLATES,
    permission_id,
    role_id,
    role_permission_id,
)


def test_permission_codes_unique() -> None:
    assert len(ALL_CODES) == len(set(ALL_CODES))
    assert len(PERMISSIONS) == len(ALL_CODES)


def test_role_templates_reference_known_codes() -> None:
    catalog = set(ALL_CODES)
    for role, codes in ROLE_TEMPLATES.items():
        assert codes, f"{role} has no permissions"
        assert len(codes) == len(set(codes)), f"{role} has duplicate codes"
        unknown = set(codes) - catalog
        assert not unknown, f"{role} references unknown codes: {unknown}"


def test_platform_admin_has_all_permissions() -> None:
    assert set(ROLE_TEMPLATES["platform_admin"]) == set(ALL_CODES)


def test_lineage_source_manage_is_least_privilege() -> None:
    # P1A-1: new deny-by-default permission, granted only to data_steward (+ platform_admin via
    # ALL_CODES); read-only roles must NOT hold it (least privilege ENT-P-01, 3L independence).
    assert "lineage.source.manage" in ALL_CODES
    assert "lineage.source.manage" in ROLE_TEMPLATES["data_steward"]
    assert "lineage.source.manage" in ROLE_TEMPLATES["platform_admin"]
    for role in ("risk_analyst_1l", "risk_manager_2l", "auditor_3l", "ops"):
        assert "lineage.source.manage" not in ROLE_TEMPLATES[role]


def test_model_inventory_register_is_least_privilege() -> None:
    # P1A-2: register granted to the 1L model developer/owner + platform_admin (via ALL_CODES);
    # NOT to the independent validator/auditor (pre-positions MG-04 dev≠validator / SOD-03).
    assert "model.inventory.register" in ALL_CODES and "model.inventory.view" in ALL_CODES
    assert "model.inventory.register" in ROLE_TEMPLATES["risk_analyst_1l"]
    assert "model.inventory.register" in ROLE_TEMPLATES["platform_admin"]
    for role in ("risk_manager_2l", "auditor_3l", "ops"):
        assert "model.inventory.register" not in ROLE_TEMPLATES[role]
    # view is held by the inventory readers.
    for role in ("risk_analyst_1l", "risk_manager_2l", "auditor_3l"):
        assert "model.inventory.view" in ROLE_TEMPLATES[role]


def test_dq_rule_manage_is_least_privilege() -> None:
    # P1A-3: dq.rule.manage stays on the data steward (+ platform_admin) only — NOT the read roles
    # (least privilege ENT-P-01; pre-positions the P7 REQ-DQR-003 override SoD where P-DS is maker).
    assert "dq.rule.manage" in ALL_CODES and "dq.result.view" in ALL_CODES
    assert "dq.rule.manage" in ROLE_TEMPLATES["data_steward"]
    assert "dq.rule.manage" in ROLE_TEMPLATES["platform_admin"]
    for role in ("risk_analyst_1l", "risk_manager_2l", "auditor_3l", "ops"):
        assert "dq.rule.manage" not in ROLE_TEMPLATES[role]
    # result.view is held broadly by the read roles.
    for role in ("data_steward", "risk_analyst_1l", "risk_manager_2l", "auditor_3l"):
        assert "dq.result.view" in ROLE_TEMPLATES[role]


def test_ids_deterministic_and_unique() -> None:
    assert permission_id("data.upload") == permission_id("data.upload")
    assert role_id("ops") == role_id("ops")

    perm_ids = [permission_id(code) for code in ALL_CODES]
    role_ids = [role_id(role) for role in ROLE_TEMPLATES]
    rp_ids = [
        role_permission_id(role, code) for role, codes in ROLE_TEMPLATES.items() for code in codes
    ]
    for ids in (perm_ids, role_ids, rp_ids):
        assert len(ids) == len(set(ids))
    assert not (set(perm_ids) & set(role_ids))
    assert not (set(rp_ids) & set(perm_ids))
