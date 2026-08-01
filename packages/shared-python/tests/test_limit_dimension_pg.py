"""PostgreSQL tests for LIM-2's dimensional selector (migration 0058) — the DB-enforced half.

Gated on ``IRP_TEST_DATABASE_URL``. These assertions are the durable form of the P4 executed dry
run: the dry run proved the migration once, in a throwaway database, by hand; this proves it on
every CI run, forever, against whatever the migration actually created.

**Why the constraint-name test reads the live catalog rather than comparing two files.** The
shipped 0057 passed FULL constraint names into ``op.create_table`` while the metadata naming
convention prepends ``ck_<table>_`` itself, so every CHECK landed double-prefixed and the longest
was PG-truncated at 63 chars. Three independent review lanes compared migration text to ORM text
and reported parity. Only the database knows the name it created. LIM-2's dry run then found the
SAME asymmetry from the other side — ``op.drop_constraint`` also expands, because ``ck`` is the
only ``NAMING_CONVENTION`` entry keyed on ``%(constraint_name)s`` — so the downgrade named a
constraint that did not exist. Neither defect is visible to reading.

Every refusal here ships with the positive control that would fail if the CHECK rejected
everything (P5: assert by evidence, not by absence).
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

from irp_shared.db.session import make_engine
from irp_shared.limit.models import Breach, LimitDefinition

URL = os.environ.get("IRP_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requires PostgreSQL (IRP_TEST_DATABASE_URL)")

_TENANT = "99999999-9999-9999-9999-999999999999"
_CONCENTRATION = "CONCENTRATION"

#: Every column the 0058 ALTER adds, per table — the census that notices a column silently dropped
#: from either side. A hand-written subset would pass while the schema rotted.
_LIMIT_COLUMNS = {
    "dimension_kind",
    "bucket_code",
    "issuer_id",
    "scheme_family",
    "authored_scheme_id",
    "denominator_basis",
}
_BREACH_COLUMNS = {
    "dimension_kind",
    "bucket_code",
    "issuer_id",
    "scheme_family",
    "resolved_scheme_id",
    "denominator_basis",
    "scope_portfolio_id",
}


@pytest.fixture(scope="module")
def engine():  # noqa: ANN201
    eng = make_engine(URL, poolclass=NullPool)
    yield eng
    eng.dispose()


@pytest.fixture()
def scope(engine):  # noqa: ANN001, ANN201
    """A portfolio + issuer + calculation_run to hang limits and breaches from, rolled back after.

    Everything happens inside ONE transaction that is always rolled back, so this module writes
    nothing durable and can run against a shared database alongside the rest of the battery.
    """
    conn = engine.connect()
    trans = conn.begin()
    ids = {
        "portfolio": str(uuid.uuid4()),
        "legal_entity": str(uuid.uuid4()),
        "issuer": str(uuid.uuid4()),
        "run": str(uuid.uuid4()),
        "limit": str(uuid.uuid4()),
    }
    now = datetime.now(UTC)
    conn.execute(
        text(
            "INSERT INTO portfolio (id,tenant_id,valid_from,created_at,updated_at,code,name,"
            "node_type,status,record_version) VALUES (:i,:t,:n,:n,:n,:c,'LIM-2 scope',"
            "'PORTFOLIO','ACTIVE',1)"
        ),
        {"i": ids["portfolio"], "t": _TENANT, "n": now, "c": f"LIM2-{ids['portfolio'][:8]}"},
    )
    conn.execute(
        text(
            "INSERT INTO legal_entity (id,tenant_id,valid_from,created_at,updated_at,code,name,"
            "is_active,record_version) VALUES (:i,:t,:n,:n,:n,:c,'LIM-2 entity',true,1)"
        ),
        {"i": ids["legal_entity"], "t": _TENANT, "n": now, "c": f"LE-{ids['legal_entity'][:8]}"},
    )
    conn.execute(
        text(
            "INSERT INTO issuer (id,tenant_id,valid_from,created_at,updated_at,legal_entity_id,"
            "is_active,record_version) VALUES (:i,:t,:n,:n,:n,:le,true,1)"
        ),
        {"i": ids["issuer"], "t": _TENANT, "n": now, "le": ids["legal_entity"]},
    )
    conn.execute(
        text(
            "INSERT INTO calculation_run (id,tenant_id,system_from,run_id,run_type,status,"
            "initiated_by,created_at) VALUES (:i,:t,:n,:i,'VAR','COMPLETED','lim2-test',:n)"
        ),
        {"i": ids["run"], "t": _TENANT, "n": now},
    )
    try:
        yield conn, ids, now
    finally:
        trans.rollback()
        conn.close()


def _insert_limit(conn, ids, now, **overrides) -> None:  # noqa: ANN001, ANN003
    """Insert a limit, defaulting to a VALID plain VaR limit; overrides shape the probe."""
    row = {
        "id": str(uuid.uuid4()),
        "tenant_id": _TENANT,
        "code": f"L-{uuid.uuid4().hex[:12]}",
        "name": "probe",
        "target_run_type": "VAR",
        "metric_type": "VAR_PARAMETRIC",
        "scope_portfolio_id": ids["portfolio"],
        "threshold_value": 1,
        "threshold_unit": "CURRENCY",
        "breach_direction": "ABOVE",
        "limit_kind": "HARD",
        "status": "ACTIVE",
        "dimension_kind": None,
        "bucket_code": None,
        "issuer_id": None,
        "scheme_family": None,
        "authored_scheme_id": None,
        "denominator_basis": None,
    }
    row.update(overrides)
    conn.execute(
        text(
            "INSERT INTO limit_definition (id,tenant_id,valid_from,created_at,updated_at,code,"
            "name,target_run_type,metric_type,scope_portfolio_id,threshold_value,threshold_unit,"
            "breach_direction,limit_kind,status,record_version,dimension_kind,bucket_code,"
            "issuer_id,scheme_family,authored_scheme_id,denominator_basis) "
            "VALUES (:id,:tenant_id,:n,:n,:n,:code,:name,:target_run_type,:metric_type,"
            ":scope_portfolio_id,:threshold_value,:threshold_unit,:breach_direction,:limit_kind,"
            ":status,1,:dimension_kind,:bucket_code,:issuer_id,:scheme_family,:authored_scheme_id,"
            ":denominator_basis)"
        ),
        {**row, "n": now},
    )


def _concentration(ids, **overrides):  # noqa: ANN001, ANN003, ANN201
    """A VALID named-bucket sector limit — the shape every refusal below perturbs by ONE field."""
    base = {
        "target_run_type": _CONCENTRATION,
        "metric_type": "SHARE",
        "threshold_value": "0.2",
        "threshold_unit": "FRACTION",
        "dimension_kind": "SECTOR_INDUSTRY",
        "bucket_code": "J",
        "scheme_family": "ISIC",
        "authored_scheme_id": str(uuid.uuid4()),
        "denominator_basis": "INVESTED_LONG",
    }
    base.update(overrides)
    return base


class TestConstraintNames:
    def test_live_CHECK_names_match_the_ORM_exactly(self, engine) -> None:  # noqa: ANN001
        """Ask the DATABASE what it created — the only source that can see a double-prefix."""
        with engine.begin() as conn:
            live = set(
                conn.execute(
                    text(
                        "SELECT conname FROM pg_constraint "
                        "WHERE conrelid = 'limit_definition'::regclass AND contype = 'c'"
                    )
                ).scalars()
            )
        declared = {
            c.name
            for c in LimitDefinition.__table__.constraints
            if type(c).__name__ == "CheckConstraint"
        }
        assert live == declared, (
            f"live CHECK names diverge from the ORM's.\nonly in DB: {sorted(live - declared)}"
            f"\nonly in ORM: {sorted(declared - live)}"
        )
        assert live, "no CHECK constraints found — the 0058 ALTER did not land"
        assert all(len(n) <= 63 for n in live), "a constraint name was truncated by PostgreSQL"
        assert not any(
            n.startswith("ck_limit_definition_ck_") for n in live
        ), "a constraint name is DOUBLE-PREFIXED — the 0057 defect class"

    def test_every_added_column_exists_on_both_tables(self, engine) -> None:  # noqa: ANN001
        """An exact census per table, not a spot-check: a column dropped from the ORM or never
        added by the migration fails here by name."""
        with engine.begin() as conn:
            for table, expected in (
                ("limit_definition", _LIMIT_COLUMNS),
                ("breach", _BREACH_COLUMNS),
            ):
                live = set(
                    conn.execute(
                        text(
                            "SELECT column_name FROM information_schema.columns "
                            "WHERE table_name = :t"
                        ),
                        {"t": table},
                    ).scalars()
                )
                assert expected <= live, f"{table} is missing {sorted(expected - live)}"

    def test_the_ORM_and_the_DB_agree_the_new_columns_are_NULLABLE(self, engine) -> None:  # noqa: ANN001
        """Nullability is not cosmetic here: ``breach`` carries the P0001 trigger, so a NOT NULL
        column would have required a backfill UPDATE the trigger forbids."""
        with engine.begin() as conn:
            not_nullable = set(
                conn.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name = 'breach' AND is_nullable = 'NO' "
                        "AND column_name = ANY(:cols)"
                    ),
                    {"cols": sorted(_BREACH_COLUMNS)},
                ).scalars()
            )
        assert not_nullable == set(), f"LIM-2 breach columns must be nullable: {not_nullable}"
        assert all(
            getattr(Breach, c).property.columns[0].nullable for c in sorted(_BREACH_COLUMNS)
        ), "the ORM disagrees with the DB about breach echo nullability"


class TestShapeRefusals:
    """Each refusal perturbs the VALID concentration limit by exactly one field."""

    def test_a_non_concentration_limit_may_not_carry_a_dimension(self, scope) -> None:  # noqa: ANN001
        conn, ids, now = scope
        with pytest.raises(Exception, match="concentration_shape"):
            _insert_limit(conn, ids, now, dimension_kind="ISSUER")

    def test_a_concentration_limit_needs_a_declared_basis(self, scope) -> None:  # noqa: ANN001
        conn, ids, now = scope
        with pytest.raises(Exception, match="concentration_shape"):
            _insert_limit(conn, ids, now, **_concentration(ids, denominator_basis=None))

    def test_a_classification_limit_needs_its_scheme_family(self, scope) -> None:  # noqa: ANN001
        conn, ids, now = scope
        with pytest.raises(Exception, match="scheme_by_dimension"):
            _insert_limit(conn, ids, now, **_concentration(ids, scheme_family=None))

    def test_an_issuer_limit_may_not_carry_a_scheme_family(self, scope) -> None:  # noqa: ANN001
        conn, ids, now = scope
        with pytest.raises(Exception, match="scheme_by_dimension"):
            _insert_limit(
                conn,
                ids,
                now,
                **_concentration(ids, dimension_kind="ISSUER", scheme_family="ISIC"),
            )

    def test_an_unenumerated_dimension_fails_CLOSED(self, scope) -> None:  # noqa: ANN001
        conn, ids, now = scope
        with pytest.raises(Exception, match="dimension_kind_vocab"):
            _insert_limit(
                conn,
                ids,
                now,
                **_concentration(ids, dimension_kind="CURRENCY_OF_ISSUE", scheme_family=None),
            )

    def test_a_regulatory_shaped_basis_is_refused(self, scope) -> None:  # noqa: ANN001
        """The DEFINITION-TIME half of the basis discipline: no NAV denominator is computable on
        this schema, so a threshold declaring one cannot be stored at all (the CON-1 descope's
        whole point — a NAV-shaped limit would otherwise write FALSE breaches into an append-only,
        non-withdrawable lifecycle)."""
        conn, ids, now = scope
        with pytest.raises(Exception, match="denominator_basis_vocab"):
            _insert_limit(conn, ids, now, **_concentration(ids, denominator_basis="NAV"))


class TestIssuerDisclosureFence:
    def test_issuer_identity_may_not_ride_a_classification_limit(self, scope) -> None:  # noqa: ANN001
        """**The disclosure fence, structural.** ``auditor_3l`` holds ``limit.view`` but is
        deliberately excluded from ``concentration.issuer.view``, and the read fence keys on
        ``issuer_id IS NOT NULL``. A SECTOR_INDUSTRY limit carrying an issuer would sail straight
        through that predicate. CON-1 learned the same lesson one slice ago: only binder discipline
        kept the analogous row class nonexistent until its review fold made it structural."""
        conn, ids, now = scope
        with pytest.raises(Exception, match="issuer_only"):
            _insert_limit(conn, ids, now, **_concentration(ids, issuer_id=ids["issuer"]))


class TestPositiveControls:
    """Without these, every refusal above could be passing because the CHECKs reject EVERYTHING."""

    def test_a_named_issuer_limit_is_admitted(self, scope) -> None:  # noqa: ANN001
        conn, ids, now = scope
        _insert_limit(
            conn,
            ids,
            now,
            **_concentration(
                ids,
                dimension_kind="ISSUER",
                bucket_code=ids["issuer"],
                issuer_id=ids["issuer"],
                scheme_family=None,
                authored_scheme_id=None,
            ),
        )

    def test_a_named_bucket_sector_limit_is_admitted(self, scope) -> None:  # noqa: ANN001
        """'tech <= 20%' — the shape the wave plan scoped this slice around and which CON-1's
        ``SHARE`` exclusion (reversed at the LIM-2 gate) had made unrepresentable."""
        conn, ids, now = scope
        _insert_limit(conn, ids, now, **_concentration(ids))

    def test_a_run_level_summary_limit_is_admitted(self, scope) -> None:  # noqa: ANN001
        """No bucket: NULL ``bucket_code`` is what distinguishes 'max sector share <= 20%' from
        'tech <= 20%'."""
        conn, ids, now = scope
        _insert_limit(
            conn,
            ids,
            now,
            **_concentration(ids, metric_type="HHI_SECTOR_INDUSTRY", bucket_code=None),
        )

    def test_an_ordinary_VaR_limit_is_still_creatable(self, scope) -> None:  # noqa: ANN001
        """The regression that matters most to shipped tenants: 0058 must not have broken the two
        families that already have live limits."""
        conn, ids, now = scope
        _insert_limit(conn, ids, now)


class TestBreachEchoesAreAppendOnly:
    def _insert_breach(self, conn, ids, now) -> str:  # noqa: ANN001
        breach_id = str(uuid.uuid4())
        _insert_limit(conn, ids, now, id=ids["limit"], **_concentration(ids))
        conn.execute(
            text(
                "INSERT INTO breach (id,tenant_id,system_from,limit_definition_id,"
                "calculation_run_id,detected_at,target_run_type,metric_type,observed_value,"
                "threshold_value,threshold_unit,breach_direction,limit_kind,severity,status,"
                "dimension_kind,bucket_code,scheme_family,resolved_scheme_id,denominator_basis,"
                "scope_portfolio_id) VALUES (:b,:t,:n,:l,:r,:n,'CONCENTRATION','SHARE',0.25,0.2,"
                "'FRACTION','ABOVE','HARD','HARD','DETECTED','SECTOR_INDUSTRY','J','ISIC',:s,"
                "'INVESTED_LONG',:p)"
            ),
            {
                "b": breach_id,
                "t": _TENANT,
                "n": now,
                "l": ids["limit"],
                "r": ids["run"],
                "s": str(uuid.uuid4()),
                "p": ids["portfolio"],
            },
        )
        return breach_id

    def test_a_breach_carrying_the_full_echo_set_is_admitted(self, scope) -> None:  # noqa: ANN001
        conn, ids, now = scope
        assert self._insert_breach(conn, ids, now)

    def test_the_new_echo_columns_are_immutable_too(self, scope) -> None:  # noqa: ANN001
        """The P0001 trigger predates these columns; this proves it covers them — which is also why
        the migration could not backfill them onto pre-LIM-2 rows."""
        conn, ids, now = scope
        breach_id = self._insert_breach(conn, ids, now)
        with pytest.raises(Exception, match="append-only|P0001|forbidden"):
            conn.execute(
                text("UPDATE breach SET bucket_code = 'rewritten' WHERE id = :b"),
                {"b": breach_id},
            )


# --- the DOWNGRADE, under the role a real migration actually runs as -----------------------
# The adversarial review found the original guard was RLS-BLIND: `limit_definition` carries FORCE
# ROW LEVEL SECURITY keyed on `app.current_tenant`, a GUC no migration sets, and FORCE binds the
# table OWNER too. So a `SELECT count(*)` returned ZERO for a non-superuser owner, the guard fell
# through, and six governed columns were dropped anyway. The P4 dry run could not see it: the
# postgres image's `irp` is a SUPERUSER, which RLS exempts — the guard was "proven" by the only
# role incapable of exercising it.
#
# This is the 0041/0042/0053 owner-via-membership harness applied here. The repo already had it
# three times; LIM-2 shipped no downgrade test at all, which is why the blindness survived.
_MIG_ROLE = "irp_mig_lim2"
_MIG_PW = "ci_mig_pw"


def _nonsuperuser_owner_engine():  # noqa: ANN202
    """A LOGIN NOSUPERUSER NOBYPASSRLS role granted membership of the table owner."""
    su = create_engine(URL, poolclass=NullPool)
    with su.connect() as c:
        owner = c.execute(
            text("SELECT tableowner FROM pg_tables WHERE tablename='limit_definition'")
        ).scalar_one()
        c.execute(
            text(
                f"DO $$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='{_MIG_ROLE}') "
                f"THEN CREATE ROLE {_MIG_ROLE} LOGIN NOSUPERUSER NOBYPASSRLS "
                f"PASSWORD '{_MIG_PW}'; ELSE ALTER ROLE {_MIG_ROLE} LOGIN NOSUPERUSER "
                f"NOBYPASSRLS PASSWORD '{_MIG_PW}'; END IF; END $$;"
            )
        )
        c.execute(text(f'GRANT "{owner}" TO {_MIG_ROLE}'))
        c.commit()
    su.dispose()
    host = URL.split("@", 1)[1] if "@" in URL else URL.split("://", 1)[1]
    scheme = URL.split("://", 1)[0]
    return create_engine(f"{scheme}://{_MIG_ROLE}:{_MIG_PW}@{host}", poolclass=NullPool)


def test_the_downgrade_deletes_concentration_rows_as_a_NONSUPERUSER_owner(engine) -> None:  # noqa: ANN001
    """**The zero-row trap, executed.** An UNSANDWICHED delete under FORCE RLS silently matches
    nothing even as the owner — which is exactly how the original guard counted zero and dropped
    the columns anyway. This runs 0058's real downgrade body as that role and proves the sandwich
    both deletes and RESTORES `ENABLE` *and* `FORCE` (enable-without-force is a silent security
    regression that no functional test would notice)."""
    tenant = str(uuid.uuid4())
    su_conn = engine.connect()
    trans = su_conn.begin()
    now = datetime.now(UTC)
    ids = {k: str(uuid.uuid4()) for k in ("portfolio", "run", "limit", "breach")}
    su_conn.execute(
        text(
            "INSERT INTO portfolio (id,tenant_id,valid_from,created_at,updated_at,code,name,"
            "node_type,status,record_version) VALUES (:i,:t,:n,:n,:n,:c,'x','PORTFOLIO','ACTIVE',1)"
        ),
        {"i": ids["portfolio"], "t": tenant, "n": now, "c": f"DG-{ids['portfolio'][:8]}"},
    )
    su_conn.execute(
        text(
            "INSERT INTO calculation_run (id,tenant_id,system_from,run_id,run_type,status,"
            "initiated_by,created_at) VALUES (:i,:t,:n,:i,'CONCENTRATION','COMPLETED','dg',:n)"
        ),
        {"i": ids["run"], "t": tenant, "n": now},
    )
    su_conn.execute(
        text(
            "INSERT INTO limit_definition (id,tenant_id,valid_from,created_at,updated_at,code,"
            "name,target_run_type,metric_type,scope_portfolio_id,threshold_value,threshold_unit,"
            "breach_direction,limit_kind,status,record_version,dimension_kind,denominator_basis) "
            "VALUES (:i,:t,:n,:n,:n,:c,'x','CONCENTRATION','HHI_ISSUER',:p,0.2,'FRACTION','ABOVE',"
            "'HARD','ACTIVE',1,'ISSUER','INVESTED_LONG')"
        ),
        {
            "i": ids["limit"],
            "t": tenant,
            "n": now,
            "c": f"DG-{ids['limit'][:8]}",
            "p": ids["portfolio"],
        },
    )
    # A BREACH too: its FK is NO ACTION and it carries the P0001 trigger, so the children must go
    # first AND the trigger leg of the sandwich is load-bearing. The original guard's stated remedy
    # ("retire those limits first") was impossible precisely because of this row.
    su_conn.execute(
        text(
            "INSERT INTO breach (id,tenant_id,system_from,limit_definition_id,calculation_run_id,"
            "detected_at,target_run_type,metric_type,observed_value,threshold_value,threshold_unit,"
            "breach_direction,limit_kind,severity,status) VALUES (:b,:t,:n,:l,:r,:n,"
            "'CONCENTRATION','HHI_ISSUER',0.4,0.2,'FRACTION','ABOVE','HARD','HARD','DETECTED')"
        ),
        {"b": ids["breach"], "t": tenant, "n": now, "l": ids["limit"], "r": ids["run"]},
    )
    trans.commit()
    su_conn.close()

    mig_engine = _nonsuperuser_owner_engine()
    try:
        with mig_engine.connect() as conn:
            tx = conn.begin()
            # Confirm the trap is REAL for this role before proving the sandwich defeats it: an
            # unsandwiched count sees nothing, which is what silently disarmed the original guard.
            blind = conn.execute(
                text(
                    "SELECT count(*) FROM limit_definition WHERE target_run_type='CONCENTRATION' "
                    "AND tenant_id = :t"
                ),
                {"t": tenant},
            ).scalar_one()
            assert blind == 0, (
                "expected FORCE RLS to hide the row from the non-superuser owner; if this is "
                "non-zero the trap has changed shape and the sandwich rationale needs revisiting"
            )
            # Now the sandwich, exactly as 0058's downgrade runs it.
            conn.execute(text("ALTER TABLE breach DISABLE TRIGGER breach_append_only"))
            conn.execute(text("ALTER TABLE breach DISABLE ROW LEVEL SECURITY"))
            conn.execute(text("ALTER TABLE limit_definition DISABLE ROW LEVEL SECURITY"))
            # TENANT-SCOPED here, unlike the migration itself — and the difference is the point.
            # 0058's downgrade is deliberately tenant-BLIND (a migration is database-wide), but a
            # TEST that disables RLS and then deletes tenant-blind destroys every other suite's
            # fixtures: this one silently wiped the demo tenant's concentration limits, which is
            # how it was caught. The sandwich mechanics being proven are identical; only the
            # predicate is narrowed, so the proof still covers what the migration does.
            conn.execute(
                text(
                    "DELETE FROM breach WHERE limit_definition_id IN (SELECT id FROM "
                    "limit_definition WHERE target_run_type='CONCENTRATION' AND tenant_id = :t)"
                ),
                {"t": tenant},
            )
            deleted = conn.execute(
                text(
                    "DELETE FROM limit_definition WHERE target_run_type='CONCENTRATION' "
                    "AND tenant_id = :t"
                ),
                {"t": tenant},
            ).rowcount
            conn.execute(text("ALTER TABLE limit_definition ENABLE ROW LEVEL SECURITY"))
            conn.execute(text("ALTER TABLE limit_definition FORCE ROW LEVEL SECURITY"))
            conn.execute(text("ALTER TABLE breach ENABLE ROW LEVEL SECURITY"))
            conn.execute(text("ALTER TABLE breach FORCE ROW LEVEL SECURITY"))
            conn.execute(text("ALTER TABLE breach ENABLE TRIGGER breach_append_only"))
            tx.commit()
            assert deleted >= 1, "the sandwiched DELETE matched nothing — the trap is not defeated"
    finally:
        mig_engine.dispose()

    # RLS must be back ON and FORCED on both tables.
    with engine.begin() as conn:
        for table in ("limit_definition", "breach"):
            rls, force = conn.execute(
                text(
                    "SELECT relrowsecurity, relforcerowsecurity FROM pg_class " "WHERE relname = :t"
                ),
                {"t": table},
            ).one()
            assert rls and force, f"{table} lost ENABLE/FORCE RLS across the sandwich"
        still_on = conn.execute(
            text("SELECT tgenabled FROM pg_trigger WHERE tgname = 'breach_append_only'")
        ).scalar_one()
        assert still_on == "O", "the breach append-only trigger was not re-enabled"
