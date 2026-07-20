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


def test_model_validate_grants_as_ratified() -> None:
    # VW-1 (OD-VW-1-E): the 2L independent-validation write. Held by risk_manager_2l (ROLE-MV) +
    # platform_admin ONLY. SOD-03: WITHHELD from risk_analyst_1l (the sole register holder) and from
    # data_steward (a maker-tier role must not gain a 2L assurance verb). auditor_3l is view-only.
    assert "model.validate" in ALL_CODES
    assert "model.validate" in ROLE_TEMPLATES["risk_manager_2l"]
    assert "model.validate" in ROLE_TEMPLATES["platform_admin"]
    for role in ("risk_analyst_1l", "data_steward", "auditor_3l", "ops"):
        assert "model.validate" not in ROLE_TEMPLATES[role], f"{role} must not hold model.validate"
    # The SoD invariant made explicit: no role holds BOTH register and validate (except admin).
    for role, codes in ROLE_TEMPLATES.items():
        if role == "platform_admin":
            continue
        assert not (
            "model.inventory.register" in codes and "model.validate" in codes
        ), f"{role} violates SOD-03 (holds both register and validate)"


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


def test_reference_data_permissions_are_additive_and_least_privilege() -> None:
    # P1B-1: the five additive reference perms exist; reference.rating.* is RESERVED
    # (future FR assignment domain) and must NOT be minted. reference.calendar.edit already existed.
    new_codes = (
        "reference.currency.view",
        "reference.currency.edit",
        "reference.rating_scale.view",
        "reference.rating_scale.edit",
        "reference.calendar.view",
    )
    for code in new_codes:
        assert code in ALL_CODES, f"missing {code}"
    assert not any(code.startswith("reference.rating.") for code in ALL_CODES)

    # .edit perms: data_steward (the maker) + platform_admin (via ALL_CODES); NOT the read tiers.
    for code in ("reference.currency.edit", "reference.rating_scale.edit"):
        assert code in ROLE_TEMPLATES["data_steward"]
        assert code in ROLE_TEMPLATES["platform_admin"]
        for role in ("risk_analyst_1l", "risk_manager_2l", "auditor_3l", "ops"):
            assert code not in ROLE_TEMPLATES[role], f"{role} must not hold {code}"

    # .view perms: data_steward + the read tiers (incl. the 3L auditor) + platform_admin.
    for code in (
        "reference.currency.view",
        "reference.rating_scale.view",
        "reference.calendar.view",
    ):
        for role in (
            "data_steward",
            "risk_analyst_1l",
            "risk_manager_2l",
            "auditor_3l",
            "platform_admin",
        ):
            assert code in ROLE_TEMPLATES[role], f"{role} should hold {code}"


def test_legal_entity_permissions_additive_and_recipient_parity() -> None:
    # P1B-2: the two additive legal_entity permissions exist; reference.rating.* still absent.
    assert "reference.legal_entity.view" in ALL_CODES
    assert "reference.legal_entity.edit" in ALL_CODES
    assert not any(code.startswith("reference.rating.") for code in ALL_CODES)

    def _holders(code: str) -> set[str]:
        return {role for role, codes in ROLE_TEMPLATES.items() if code in codes}

    # legal_entity is PROPRIETARY identity -> .view recipients EQUAL the issuer/counterparty set
    # (data_steward/risk_analyst_1l/risk_manager_2l + platform_admin), and EXCLUDE auditor_3l. The
    # parity assertion is the regression guard so the proprietary-identity family cannot drift.
    assert _holders("reference.legal_entity.view") == _holders("reference.issuer.view")
    assert _holders("reference.legal_entity.view") == _holders("reference.counterparty.view")
    assert "auditor_3l" not in _holders("reference.legal_entity.view")
    assert _holders("reference.legal_entity.view") == {
        "data_steward",
        "risk_analyst_1l",
        "risk_manager_2l",
        "platform_admin",
    }
    # .edit: data_steward (the maker) + platform_admin only; never the read tiers.
    assert _holders("reference.legal_entity.edit") == {"data_steward", "platform_admin"}


def test_identifier_permissions_additive_and_recipient_parity() -> None:
    # P1B-3: the two additive identifier permissions exist; reference.rating.* still absent.
    assert "reference.identifier.view" in ALL_CODES
    assert "reference.identifier.edit" in ALL_CODES
    assert not any(code.startswith("reference.rating.") for code in ALL_CODES)

    def _holders(code: str) -> set[str]:
        return {role for role, codes in ROLE_TEMPLATES.items() if code in codes}

    # P1B-3 is purely ADDITIVE: the new .view recipients EQUAL the reference.instrument.view set
    # (proprietary security-master SoD — EXCLUDES auditor_3l), and the pre-existing
    # reference.identifier.resolve recipient set is UNCHANGED (NOT widened to risk_manager_2l).
    assert _holders("reference.identifier.view") == _holders("reference.instrument.view")
    assert _holders("reference.identifier.view") == {
        "data_steward",
        "risk_analyst_1l",
        "risk_manager_2l",
        "platform_admin",
    }
    # .edit: data_steward (the maker) + platform_admin only.
    assert _holders("reference.identifier.edit") == {"data_steward", "platform_admin"}
    # .resolve: pre-existing recipients UNCHANGED — risk_manager_2l must NOT be granted resolve.
    assert _holders("reference.identifier.resolve") == {
        "data_steward",
        "risk_analyst_1l",
        "platform_admin",
    }
    assert "risk_manager_2l" not in _holders("reference.identifier.resolve")
    # auditor_3l excluded from all three (proprietary-identity SoD).
    for code in (
        "reference.identifier.view",
        "reference.identifier.edit",
        "reference.identifier.resolve",
    ):
        assert "auditor_3l" not in _holders(code)


def test_corporate_action_permissions_additive_and_recipient_parity() -> None:
    # P1B-4: the additive corporate_action.view exists; .edit already existed; rating.* absent.
    assert "reference.corporate_action.view" in ALL_CODES
    assert "reference.corporate_action.edit" in ALL_CODES
    assert not any(code.startswith("reference.rating.") for code in ALL_CODES)

    def _holders(code: str) -> set[str]:
        return {role for role, codes in ROLE_TEMPLATES.items() if code in codes}

    # Purely ADDITIVE: the new .view recipients EQUAL the reference.instrument.view set
    # (proprietary security-master SoD — EXCLUDES auditor_3l). .edit recipients are UNCHANGED.
    assert _holders("reference.corporate_action.view") == _holders("reference.instrument.view")
    assert _holders("reference.corporate_action.view") == {
        "data_steward",
        "risk_analyst_1l",
        "risk_manager_2l",
        "platform_admin",
    }
    assert _holders("reference.corporate_action.edit") == {"data_steward", "platform_admin"}
    for code in ("reference.corporate_action.view", "reference.corporate_action.edit"):
        assert "auditor_3l" not in _holders(code)


def test_portfolio_permissions_grants_as_ratified() -> None:
    # P1C-1: portfolio.view/edit pre-exist in the catalog (placeholders). The additive GRANT
    # (OD-P1C1-3): data_steward holds BOTH view + edit (the maker reads its own writes). The read
    # tiers (risk_analyst_1l/risk_manager_2l) already hold view (unchanged). edit is maker/admin
    # only
    # (data_steward + platform_admin). auditor_3l EXCLUDED (scope SoD).
    assert "portfolio.view" in ALL_CODES and "portfolio.edit" in ALL_CODES

    def _holders(code: str) -> set[str]:
        return {role for role, codes in ROLE_TEMPLATES.items() if code in codes}

    assert _holders("portfolio.view") == {
        "data_steward",
        "risk_analyst_1l",
        "risk_manager_2l",
        "platform_admin",
    }
    assert _holders("portfolio.edit") == {"data_steward", "platform_admin"}
    assert "auditor_3l" not in _holders("portfolio.view")
    assert "auditor_3l" not in _holders("portfolio.edit")


def test_transaction_permissions_grants_as_ratified() -> None:
    # P1C-2: transaction.view + transaction.record are NEWLY minted (additive). data_steward is the
    # maker/recorder (holds BOTH); transaction.record is maker/admin only; the read tiers hold view;
    # auditor_3l EXCLUDED (operational client data SoD). `.record` is the append-only governed verb.
    assert "transaction.view" in ALL_CODES and "transaction.record" in ALL_CODES

    def _holders(code: str) -> set[str]:
        return {role for role, codes in ROLE_TEMPLATES.items() if code in codes}

    assert _holders("transaction.view") == {
        "data_steward",
        "risk_analyst_1l",
        "risk_manager_2l",
        "platform_admin",
    }
    assert _holders("transaction.record") == {"data_steward", "platform_admin"}
    assert "auditor_3l" not in _holders("transaction.view")
    assert "auditor_3l" not in _holders("transaction.record")


def test_position_permissions_grants_as_ratified() -> None:
    # P1C-3: position.view PRE-EXISTS (seeded placeholder, held by the read tiers + admin); P1C-3
    # WIRES it by adding the data_steward grant. position.edit is the ONE genuinely NEW code
    # (maker/admin only). data_steward is the maker; auditor_3l EXCLUDED (proprietary holdings SoD).
    assert "position.view" in ALL_CODES and "position.edit" in ALL_CODES

    def _holders(code: str) -> set[str]:
        return {role for role, codes in ROLE_TEMPLATES.items() if code in codes}

    assert _holders("position.view") == {
        "data_steward",
        "risk_analyst_1l",
        "risk_manager_2l",
        "platform_admin",
    }
    assert _holders("position.edit") == {"data_steward", "platform_admin"}
    assert "auditor_3l" not in _holders("position.view")
    assert "auditor_3l" not in _holders("position.edit")


def test_valuation_permissions_grants_as_ratified() -> None:
    # P1C-4: BOTH valuation.view + valuation.edit are NEWLY minted (neither pre-existed in the
    # catalog, unlike position.view). data_steward is the maker (holds both); the read tiers hold
    # view; valuation.edit is maker/admin only; auditor_3l EXCLUDED from both (OD-P1C4-2).
    assert "valuation.view" in ALL_CODES and "valuation.edit" in ALL_CODES

    def _holders(code: str) -> set[str]:
        return {role for role, codes in ROLE_TEMPLATES.items() if code in codes}

    assert _holders("valuation.view") == {
        "data_steward",
        "risk_analyst_1l",
        "risk_manager_2l",
        "platform_admin",
    }
    assert _holders("valuation.edit") == {"data_steward", "platform_admin"}
    assert "auditor_3l" not in _holders("valuation.view")
    assert "auditor_3l" not in _holders("valuation.edit")


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


def test_commitment_permissions_grants_as_ratified() -> None:
    # CC-1 (OD-CC-1-B, ratified 2026-07-20): the THREE-code private-capital mint — `.edit` the FR
    # maker (commitment capture/supersede/correct), `.record` the IA maker (call/distribution
    # capture incl. reversals), `.view` reads all three tables. Both maker holder sets are
    # IDENTICAL (data_steward + platform_admin) and auditor_3l is excluded from all three
    # (captured-input read scope — the marketdata/valuation precedent). Both directions pinned.
    for code in ("commitment.view", "commitment.edit", "commitment.record"):
        assert code in ALL_CODES

    def _holders(code: str) -> set[str]:
        return {role for role, codes in ROLE_TEMPLATES.items() if code in codes}

    assert _holders("commitment.view") == {
        "data_steward",
        "risk_analyst_1l",
        "risk_manager_2l",
        "platform_admin",
    }
    assert _holders("commitment.edit") == {"data_steward", "platform_admin"}
    assert _holders("commitment.record") == {"data_steward", "platform_admin"}
    for code in ("commitment.view", "commitment.edit", "commitment.record"):
        assert "auditor_3l" not in _holders(code)


def test_pacing_permissions_grants_as_ratified() -> None:
    # CC-2 (OD-CC-2-E, ratified 2026-07-20): the pacing R-07 mint — `pacing.run` the maker (a
    # projection is *run*), `pacing.view` the read. A governed OUTPUT read INCLUDES auditor_3l
    # (the perf.view precedent), UNLIKE the captured-input `commitment.*` verbs. Maker/read sets
    # mirror the perf family. Both directions pinned.
    for code in ("pacing.run", "pacing.view"):
        assert code in ALL_CODES

    def _holders(code: str) -> set[str]:
        return {role for role, codes in ROLE_TEMPLATES.items() if code in codes}

    assert _holders("pacing.run") == {
        "data_steward",
        "risk_analyst_1l",
        "platform_admin",
    }
    assert _holders("pacing.view") == {
        "data_steward",
        "risk_analyst_1l",
        "risk_manager_2l",
        "auditor_3l",
        "platform_admin",
    }
    assert "auditor_3l" not in _holders("pacing.run")
