"""SQLite-local unit/behavior tests for generic ingestion staging (P1A-4, REQ-INT-001).

RLS is a no-op on SQLite, so isolation/fail-closed/append-only-trigger proofs live in
``test_ingestion_pg.py``; here we prove the anti-corruption layer, the compose-the-rails flow
(lineage origin + DQ + audit), the **durable-evidence / no-silent-failure** contract (the headline:
a DQ ERROR persists a REJECTED batch + flagged result + audit, never silently rolled back), the
status-mutable batch vs immutable staged record, the import-direction guard, and the scope fence.
"""

from __future__ import annotations

import json
import pathlib
import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from irp_shared.audit.models import AppendOnlyViolation, AuditEvent
from irp_shared.audit.service import verify_chain
from irp_shared.dq.models import DataQualityResult
from irp_shared.dq.rules import (
    REGISTRY,
    RULE_TYPE_ALLOWED_VALUES,
    RULE_TYPE_NOT_NULL,
    RULE_TYPE_RANGE,
)
from irp_shared.dq.service import register_dq_rule
from irp_shared.ingestion import anticorruption as ac
from irp_shared.ingestion.anticorruption import (
    EmptyFile,
    EncodingInvalid,
    FilenameUnsafe,
    FileTypeNotAllowed,
    MalformedContent,
    neutralize_cell,
    parse_csv,
    sanitize_filename,
    validate_file_type,
)
from irp_shared.ingestion.models import (
    SCAN_SKIPPED,
    STATUS_COMPLETED,
    STATUS_COMPLETED_WITH_WARNINGS,
    STATUS_REJECTED,
    IngestionBatch,
    IngestionStagedRecord,
)
from irp_shared.ingestion.service import (
    INGEST_EVENT,
    STAGING_ROW_TARGET,
    IngestionRejected,
    stage_upload,
)
from irp_shared.lineage.models import LineageEdge
from irp_shared.lineage.service import DataSourceNotVisible, register_data_source
from irp_shared.temporal import TemporalClass


def _tenant() -> str:
    return str(uuid.uuid4())


def _source(session: Session, tenant: str) -> str:
    src = register_data_source(
        session, tenant_id=tenant, code="SRC", name="Src", source_type="upload", actor_id="a"
    )
    return src.id


def _rule(
    session: Session,
    tenant: str,
    *,
    code: str = "CCY",
    rule_type: str = RULE_TYPE_ALLOWED_VALUES,
    severity: str = "ERROR",
    params: dict | None = None,
) -> None:
    register_dq_rule(
        session,
        tenant_id=tenant,
        code=code,
        name="rule",
        rule_type=rule_type,
        actor_id="a",
        params=params if params is not None else {"column": "ccy", "allowed": ["USD", "EUR"]},
        target_entity_type=STAGING_ROW_TARGET,
        severity=severity,
    )


def _events(session: Session, event_type: str) -> int:
    return session.execute(
        select(func.count()).select_from(AuditEvent).where(AuditEvent.event_type == event_type)
    ).scalar_one()


# --- temporal classes ---


def test_temporal_classes() -> None:
    assert IngestionBatch.__temporal_class__ == TemporalClass.IMMUTABLE_APPEND_ONLY
    assert IngestionStagedRecord.__temporal_class__ == TemporalClass.IMMUTABLE_APPEND_ONLY
    assert hasattr(IngestionBatch, "system_from") and hasattr(IngestionBatch, "status")


# --- anti-corruption layer (THR-05 / THR-06) ---


def test_sanitize_filename_strips_path_and_rejects_traversal() -> None:
    # Directory components (incl. traversal) are stripped to a safe basename — never a path.
    assert sanitize_filename("/etc/passwd") == "passwd"
    assert sanitize_filename("data.csv") == "data.csv"
    assert sanitize_filename("C:\\evil\\x.csv") == "x.csv"
    assert sanitize_filename("../../etc/shadow") == "shadow"
    # A name that REDUCES to nothing safe (or carries a null byte) is rejected outright.
    for bad in ("..", ".", "x\x00.csv", "", None):
        with pytest.raises(FilenameUnsafe):
            sanitize_filename(bad)  # type: ignore[arg-type]


def test_validate_file_type_csv_only() -> None:
    validate_file_type("a.csv", "text/csv")
    validate_file_type("a.csv", None)
    for name in ("a.xlsx", "a.exe", "a.csv.exe", "a"):
        with pytest.raises(FileTypeNotAllowed):
            validate_file_type(name, "text/csv")
    with pytest.raises(FileTypeNotAllowed):
        validate_file_type("a.csv", "application/x-msdownload")


def test_decode_and_parse_errors() -> None:
    with pytest.raises(EmptyFile):
        ac.decode_text(b"")
    with pytest.raises(EncodingInvalid):
        ac.decode_text(b"\xff\xfe\x00bad")
    with pytest.raises(MalformedContent):
        parse_csv("\n")  # no usable header
    with pytest.raises(EmptyFile):
        parse_csv("name,amount\n")  # header but no data rows


def test_neutralize_cell_and_parse_neutralizes_formulas() -> None:
    for danger in ("=SUM(A1)", "+1", "-1", "@cmd", "\tx", "\rx"):
        assert neutralize_cell(danger) == "'" + danger
    assert neutralize_cell("plain") == "plain"
    rows = parse_csv("name\n=SUM(A1)\n")
    assert rows[0]["name"] == "'=SUM(A1)"


def test_ragged_row_with_surplus_formula_cells_is_rejected() -> None:
    # SEC: a row WIDER than the header would land surplus cells in a list that bypasses per-cell
    # neutralization — reject the ragged row so no un-neutralized formula cell can be staged.
    with pytest.raises(MalformedContent):
        parse_csv("a,b\n=cmd,+evil,@danger,-x\n")


def test_scan_seam_returns_non_clean_placeholder() -> None:
    assert ac.scan_for_malware(b"anything") == SCAN_SKIPPED


# --- compose-the-rails happy path ---


def test_happy_path_stages_runs_dq_and_records_lineage(session: Session) -> None:
    tenant = _tenant()
    source_id = _source(session, tenant)
    _rule(session, tenant)  # ALLOWED_VALUES ccy in {USD,EUR}, ERROR
    batch = stage_upload(
        session,
        tenant_id=tenant,
        data_source_id=source_id,
        filename="prices.csv",
        content_type="text/csv",
        raw_bytes=b"ccy\nUSD\nEUR\n",
        actor_id="steward",
    )
    assert batch.status == STATUS_COMPLETED
    assert batch.scan_status == SCAN_SKIPPED
    assert batch.row_count == 2 and batch.staged_count == 2 and batch.failed_count == 0
    staged = (
        session.execute(
            select(IngestionStagedRecord).where(IngestionStagedRecord.batch_id == batch.id)
        )
        .scalars()
        .all()
    )
    assert len(staged) == 2 and {s.payload["ccy"] for s in staged} == {"USD", "EUR"}
    # DQ result links back to the batch via the populated placeholder (ingestion_batch_id).
    result = session.execute(
        select(DataQualityResult).where(DataQualityResult.ingestion_batch_id == batch.id)
    ).scalar_one()
    assert result.target_entity_type == "ingestion_batch" and result.outcome == "PASS"
    # Lineage ORIGIN edge data_source -> ingestion_batch.
    edge = session.execute(
        select(LineageEdge).where(LineageEdge.target_entity_id == batch.id)
    ).scalar_one()
    assert edge.source_id == source_id and edge.target_entity_type == "ingestion_batch"
    # Audit: DATA.INGEST create + terminal (2), DATA.VALIDATE for the run (1); chain intact.
    assert _events(session, INGEST_EVENT) == 2
    assert _events(session, "DATA.VALIDATE") == 1
    assert verify_chain(session, tenant).ok is True


# --- the headline: DQ ERROR is durable evidence, never silently rolled back (CTRL-029) ---


def test_dq_error_rejects_batch_and_persists_evidence(session: Session) -> None:
    tenant = _tenant()
    source_id = _source(session, tenant)
    _rule(session, tenant)  # ERROR severity
    with pytest.raises(IngestionRejected) as exc:
        stage_upload(
            session,
            tenant_id=tenant,
            data_source_id=source_id,
            filename="bad.csv",
            content_type="text/csv",
            raw_bytes=b"ccy\nUSD\nZZZ\n",  # ZZZ not allowed -> ERROR FAIL
            actor_id="steward",
        )
    batch = exc.value.batch
    assert batch.status == STATUS_REJECTED and exc.value.reason == "dq_failed"
    # Evidence survives in the live transaction (NOT rolled back): batch + FAIL result + audit.
    persisted = session.get(IngestionBatch, batch.id)
    assert persisted is not None and persisted.status == STATUS_REJECTED
    result = session.execute(
        select(DataQualityResult).where(DataQualityResult.ingestion_batch_id == batch.id)
    ).scalar_one()
    assert result.passed is False and result.outcome == "FAIL"
    # DATA.VALIDATE outcome='failure' (no-silent-failure) and a DATA.INGEST terminal failure event.
    dv = (
        session.execute(
            select(AuditEvent)
            .where(AuditEvent.event_type == "DATA.VALIDATE")
            .order_by(AuditEvent.sequence_no.desc())
        )
        .scalars()
        .first()
    )
    assert dv.outcome == "failure"
    terminal = (
        session.execute(
            select(AuditEvent).where(
                AuditEvent.event_type == INGEST_EVENT, AuditEvent.action == "status_change"
            )
        )
        .scalars()
        .all()
    )
    assert len(terminal) == 1 and terminal[0].outcome == "failure"
    assert terminal[0].after_value["reason"] == "dq_failed"
    # Lineage origin is recorded for EVERY persisted batch, including a REJECTED one (invariant 3).
    edge = session.execute(
        select(LineageEdge).where(LineageEdge.target_entity_id == batch.id)
    ).scalar_one()
    assert edge.source_id == source_id and edge.target_entity_type == "ingestion_batch"


def test_warning_rule_completes_with_warnings(session: Session) -> None:
    tenant = _tenant()
    source_id = _source(session, tenant)
    _rule(session, tenant, severity="WARNING")
    batch = stage_upload(
        session,
        tenant_id=tenant,
        data_source_id=source_id,
        filename="warn.csv",
        content_type="text/csv",
        raw_bytes=b"ccy\nUSD\nZZZ\n",  # ZZZ -> WARN (flag, non-blocking)
        actor_id="steward",
    )
    assert batch.status == STATUS_COMPLETED_WITH_WARNINGS and batch.failed_count == 1
    # The WARN result is also linked to the batch (set-before-flush is outcome-independent).
    result = session.execute(
        select(DataQualityResult).where(DataQualityResult.ingestion_batch_id == batch.id)
    ).scalar_one()
    assert result.outcome == "WARN"


def test_empty_active_rule_set_fails_closed(session: Session) -> None:
    # No active staging rule -> the gate finds no recorded checks -> REJECTED (fail-closed).
    tenant = _tenant()
    source_id = _source(session, tenant)
    with pytest.raises(IngestionRejected) as exc:
        stage_upload(
            session,
            tenant_id=tenant,
            data_source_id=source_id,
            filename="norules.csv",
            content_type="text/csv",
            raw_bytes=b"ccy\nUSD\n",
            actor_id="steward",
        )
    assert exc.value.reason == "dq_gate_failed" and exc.value.batch.status == STATUS_REJECTED


# --- anti-corruption rejection via the flow (auditable, no orphan) ---


def test_bad_filetype_rejected_and_audited(session: Session) -> None:
    tenant = _tenant()
    source_id = _source(session, tenant)
    _rule(session, tenant)
    with pytest.raises(IngestionRejected) as exc:
        stage_upload(
            session,
            tenant_id=tenant,
            data_source_id=source_id,
            filename="evil.exe",
            content_type="application/x-msdownload",
            raw_bytes=b"ccy\nUSD\n",
            actor_id="steward",
        )
    batch = exc.value.batch
    assert batch.status == STATUS_REJECTED and exc.value.reason == "file_type_not_allowed"
    # No rows staged, but the rejection is auditable (create + terminal DATA.INGEST events exist).
    assert (
        session.execute(
            select(func.count())
            .select_from(IngestionStagedRecord)
            .where(IngestionStagedRecord.batch_id == batch.id)
        ).scalar_one()
        == 0
    )
    assert _events(session, INGEST_EVENT) == 2


def test_formula_injection_neutralized_in_staged_payload(session: Session) -> None:
    tenant = _tenant()
    source_id = _source(session, tenant)
    _rule(session, tenant, code="NN", rule_type=RULE_TYPE_NOT_NULL, params={"column": "name"})
    batch = stage_upload(
        session,
        tenant_id=tenant,
        data_source_id=source_id,
        filename="f.csv",
        content_type="text/csv",
        raw_bytes=b"name\n=SUM(A1)\n",
        actor_id="steward",
    )
    assert batch.status == STATUS_COMPLETED
    staged = session.execute(
        select(IngestionStagedRecord).where(IngestionStagedRecord.batch_id == batch.id)
    ).scalar_one()
    assert staged.payload["name"] == "'=SUM(A1)"  # neutralized, not raw


def test_ragged_formula_row_rejected_no_smuggled_cells(session: Session) -> None:
    # SEC end-to-end: a too-wide row that tries to smuggle formula cells past neutralization is
    # rejected as malformed — and nothing is staged for the batch.
    tenant = _tenant()
    source_id = _source(session, tenant)
    _rule(session, tenant, code="NN", rule_type=RULE_TYPE_NOT_NULL, params={"column": "a"})
    with pytest.raises(IngestionRejected) as exc:
        stage_upload(
            session,
            tenant_id=tenant,
            data_source_id=source_id,
            filename="ragged.csv",
            content_type="text/csv",
            raw_bytes=b"a,b\nok,ok,=cmd,@danger\n",  # surplus formula cells
            actor_id="a",
        )
    assert exc.value.reason == "malformed_content"
    assert (
        session.execute(
            select(func.count())
            .select_from(IngestionStagedRecord)
            .where(IngestionStagedRecord.batch_id == exc.value.batch.id)
        ).scalar_one()
        == 0
    )


def test_overlong_content_type_is_bounded_not_500(session: Session) -> None:
    # SEC: an over-length content_type that still passes the `;`-split allowlist must be bounded to
    # the column width (varchar(100)) — never raise a truncation error before staging.
    tenant = _tenant()
    source_id = _source(session, tenant)
    _rule(session, tenant)
    batch = stage_upload(
        session,
        tenant_id=tenant,
        data_source_id=source_id,
        filename="ok.csv",
        content_type="text/csv;" + "a" * 300,
        raw_bytes=b"ccy\nUSD\n",
        actor_id="a",
    )
    assert batch.status == STATUS_COMPLETED
    assert batch.content_type is not None and len(batch.content_type) <= 100


def test_audit_after_value_carries_no_raw_payload_and_sanitized_filename(session: Session) -> None:
    # Invariant 4: audit after_value carries metadata/reason ONLY (no raw payload), and the stored
    # filename is the sanitized basename — even for a path-traversal client name.
    tenant = _tenant()
    source_id = _source(session, tenant)
    _rule(session, tenant)
    secret = "SECRET_CELL_VALUE_42"
    batch = stage_upload(
        session,
        tenant_id=tenant,
        data_source_id=source_id,
        filename="../../etc/prices.csv",
        content_type="text/csv",
        raw_bytes=f"ccy,note\nUSD,{secret}\n".encode(),
        actor_id="a",
    )
    assert batch.status == STATUS_COMPLETED and batch.filename == "prices.csv"  # traversal stripped
    events = (
        session.execute(select(AuditEvent).where(AuditEvent.event_type == INGEST_EVENT))
        .scalars()
        .all()
    )
    assert events
    for ev in events:
        assert secret not in json.dumps(ev.after_value)  # no raw cell value in the audit trail
        assert ev.after_value["filename"] == "prices.csv"  # sanitized basename only
    # The secret IS stored in the (RLS-scoped, non-audit) staged payload — proving it was ingested.
    staged = (
        session.execute(
            select(IngestionStagedRecord).where(IngestionStagedRecord.batch_id == batch.id)
        )
        .scalars()
        .all()
    )
    assert any(s.payload.get("note") == secret for s in staged)


def test_cross_tenant_or_unknown_source_fails_closed(session: Session) -> None:
    tenant = _tenant()
    with pytest.raises(DataSourceNotVisible):
        stage_upload(
            session,
            tenant_id=tenant,
            data_source_id=str(uuid.uuid4()),  # no such source
            filename="x.csv",
            content_type="text/csv",
            raw_bytes=b"ccy\nUSD\n",
            actor_id="a",
        )
    assert session.execute(select(func.count()).select_from(IngestionBatch)).scalar_one() == 0


# --- temporal: staged record immutable (ORM guard), batch status-mutable ---


def test_staged_record_is_append_only(session: Session) -> None:
    tenant = _tenant()
    rec = IngestionStagedRecord(
        tenant_id=tenant, batch_id=str(uuid.uuid4()), row_number=0, payload={"a": 1}
    )
    session.add(rec)
    session.commit()
    rec.payload = {"a": 2}
    with pytest.raises(AppendOnlyViolation):
        session.flush()
    session.rollback()
    session.delete(session.get(IngestionStagedRecord, rec.id))
    with pytest.raises(AppendOnlyViolation):
        session.flush()
    session.rollback()


def test_batch_status_is_mutable(session: Session) -> None:
    # The CalculationRun precedent: IA-classed but status-mutable (no ORM guard) -> UPDATE succeeds.
    tenant = _tenant()
    batch = IngestionBatch(
        tenant_id=tenant,
        data_source_id=str(uuid.uuid4()),
        filename="m.csv",
        byte_size=3,
        status="RECEIVED",
    )
    session.add(batch)
    session.commit()
    batch.status = STATUS_COMPLETED
    session.flush()  # no AppendOnlyViolation
    assert session.get(IngestionBatch, batch.id).status == STATUS_COMPLETED


# --- fail-closed audit (AUD-04 / CTRL-032) ---


def _raise_audit(*_a: object, **_k: object) -> None:
    raise RuntimeError("audit capture failed")


def test_upload_rolls_back_when_audit_fails(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    import irp_shared.ingestion.service as svc

    tenant = _tenant()
    source_id = _source(session, tenant)
    session.commit()
    monkeypatch.setattr(svc, "record_event", _raise_audit)
    with pytest.raises(RuntimeError):
        stage_upload(
            session,
            tenant_id=tenant,
            data_source_id=source_id,
            filename="x.csv",
            content_type="text/csv",
            raw_bytes=b"ccy\nUSD\n",
            actor_id="a",
        )
    session.rollback()
    assert session.execute(select(func.count()).select_from(IngestionBatch)).scalar_one() == 0


# --- scope fence + import direction ---


def test_scope_fence_generic_only(session: Session) -> None:
    # Staged record is generic: NO domain column, only id/tenant/system_from/batch/row/payload.
    cols = set(IngestionStagedRecord.__table__.columns.keys())
    assert cols == {"id", "tenant_id", "system_from", "batch_id", "row_number", "payload"}
    # No FK to any domain/canonical table; batch FK only to data_source, staged FK only to batch.
    batch_fks = {fk.column.table.name for fk in IngestionBatch.__table__.foreign_keys}
    staged_fks = {fk.column.table.name for fk in IngestionStagedRecord.__table__.foreign_keys}
    assert batch_fks == {"data_source"} and staged_fks == {"ingestion_batch"}
    # The DQ engine is reused, not extended by ingestion: the three generic evaluators (RANGE added
    # P2-2 for FX, not by ingestion) and no domain evaluators.
    assert set(REGISTRY) == {RULE_TYPE_NOT_NULL, RULE_TYPE_ALLOWED_VALUES, RULE_TYPE_RANGE}
    # No reserved P7 codes emitted on the ingest path.
    tenant = _tenant()
    source_id = _source(session, tenant)
    _rule(session, tenant)
    stage_upload(
        session,
        tenant_id=tenant,
        data_source_id=source_id,
        filename="ok.csv",
        content_type="text/csv",
        raw_bytes=b"ccy\nUSD\n",
        actor_id="a",
    )
    for code in ("DATA.RECONCILE", "DATA.CORRECTION", "DATA.PURGE"):
        assert _events(session, code) == 0


def test_ingestion_import_direction() -> None:
    # ingestion may import lineage/dq/audit/db — but NOT backend, the model registry
    # (irp_shared.model), or the plural aggregator (irp_shared.models, the real cycle vector).
    import irp_shared.ingestion as ing_pkg

    forbidden = ("irp_backend", "irp_shared.model", "irp_shared.models")
    ing_dir = pathlib.Path(ing_pkg.__file__).parent
    for py in sorted(ing_dir.glob("*.py")):
        for line in py.read_text().splitlines():
            stripped = line.strip()
            mods: list[str] = []
            if stripped.startswith("from "):
                base = stripped.split()[1]
                mods.append(base)
                # `from A import B, C` also imports the modules A.B / A.C — check those too, so
                # `from irp_shared import models` (mod 'irp_shared.models') cannot slip through.
                if " import " in stripped:
                    for name in stripped.split(" import ", 1)[1].replace("(", "").split(","):
                        token = name.strip().split(" as ")[0].strip()
                        if token and token != "*":
                            mods.append(f"{base}.{token}")
            elif stripped.startswith("import "):
                mods.append(stripped.split()[1].split(",")[0])
            else:
                continue
            for mod in mods:
                for root in forbidden:
                    assert mod != root and not mod.startswith(
                        root + "."
                    ), f"{py.name} imports {mod}"


def test_rails_do_not_import_ingestion() -> None:
    # The shipped rails must not depend back on ingestion (one-way dependency).
    import irp_shared.dq as dq_pkg
    import irp_shared.lineage as lin_pkg
    import irp_shared.model as mdl_pkg

    for pkg in (dq_pkg, lin_pkg, mdl_pkg):
        pkg_dir = pathlib.Path(pkg.__file__).parent
        for py in sorted(pkg_dir.glob("*.py")):
            text = py.read_text()
            assert "irp_shared.ingestion" not in text, f"{pkg.__name__}/{py.name} imports ingestion"
