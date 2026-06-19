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
