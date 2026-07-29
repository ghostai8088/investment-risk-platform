"""REF-1 demo stage 18 — the platform's FIRST classified book (ENT-066/067/068).

**Counts do NOT move — 25/40/133 stays 25/40/133.** A capture-only stage mints no model code, files
no validation and creates no calculation run; only the pin's POSITION relays to this stage's suite,
which now collates last. That is the CC-1 stage-8 shape ("the suite asserts the counts did NOT
move"), and it is why the pin must live HERE: a pin that collates BEFORE the newest stage cannot
see what that stage did, which is exactly the defect the SCH-2 run count (109 vs 110) recorded.

**This stage does three things, and the third is the one the next slice depends on.**

1. Seeds the SYSTEM-tenant global taxonomy: an ISIC Rev. 5 skeleton (sections → divisions) and an
   ISO 3166-1 country scheme. SYSTEM-tenant rows, so every tenant reads them and none can write
   them — the AD-013-R2 hybrid arms, exercised on real data rather than only in a policy test.
2. Creates the demo's FIRST issuers (a new fixture domain — no demo fixture has ever created one),
   each with a legal-entity core, and classifies them.
3. **BACKFILLS ``issuer_id`` onto the instruments that already carry positions and exposures.**
   Without this, CON-1's demo would compute concentration over a book whose every instrument has a
   NULL issuer — a demo that cannot REACH the control it exists to show (the OPS-1 standing
   lesson), one slice before CON-1 discovers it.

**Economic realism** (the TD-1 rule): a plausible three-sector, three-country mix for a global
multi-asset book — a US manufacturer, a German industrial, and a US private-equity holding — not
extremes. Country-of-risk is captured on the IMMEDIATE_ISSUER_RESIDENCE basis and says so, because
the whole point of the basis discriminator is that a later reader knows WHICH convention produced
the number.

**Stage ORDERING is load-bearing.** Local batteries collect alphabetically and earlier suites pin
governed sets with set-equality, so each stage appends one more ``z``. SR-1's suite is
``stage9zzzzzzzz`` (eight), so REF-1's is ``stage9zzzzzzzzz`` (NINE) — verified by ``ls``, not read
off a record (the trap RM-1 fell into).
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from irp_shared.classification.models import (
    BASIS_IMMEDIATE_ISSUER_RESIDENCE,
    BASIS_NOT_APPLICABLE,
    DIMENSION_KIND_COUNTRY_OF_RISK,
    DIMENSION_KIND_SECTOR_INDUSTRY,
    SCHEME_FAMILY_ISIC,
    SCHEME_FAMILY_ISO_3166_1,
    ClassificationScheme,
)
from irp_shared.classification.service import (
    ClassificationActor,
    capture_assignment,
    create_node,
    create_scheme,
)
from irp_shared.demo.campaign import DEMO_TENANT_ID
from irp_shared.entitlement.bootstrap import SYSTEM_TENANT_ID
from irp_shared.reference.instrument import update_instrument
from irp_shared.reference.issuer import create_issuer
from irp_shared.reference.legal_entity import create_legal_entity
from irp_shared.reference.models import Instrument
from irp_shared.reference.service import ReferenceActor

DEMO_ACTOR_ID = "demo_data_steward"

#: The exact authority versions this stage seeds (also its refuse-not-skip identity).
_ISIC_VERSION = "Rev. 5"
_COUNTRY_VERSION = "2026"

#: ISIC Rev. 5 skeleton — sections (level 1) and the divisions the demo book needs (level 2).
#: Deliberately a SKELETON, not the full 463-class scheme: a demo proves the rails, and a partial
#: authority extract is honest as long as it is labelled one.
_ISIC_SECTIONS: tuple[tuple[str, str], ...] = (
    ("C", "Manufacturing"),
    ("K", "Financial and insurance activities"),
)
_ISIC_DIVISIONS: tuple[tuple[str, str, str], ...] = (
    ("C26", "Manufacture of computer, electronic and optical products", "C"),
    ("C28", "Manufacture of machinery and equipment n.e.c.", "C"),
    ("K64", "Financial service activities, except insurance and pension funding", "K"),
)

#: ISO 3166-1 alpha-2 (the ratified canonical form; alpha-3 / M49 numeric deferred).
_COUNTRIES: tuple[tuple[str, str], ...] = (("US", "United States of America"), ("DE", "Germany"))

#: The demo's first issuers, and the campaign instrument each one issues.
_ISSUERS: tuple[tuple[str, str, str, str, str], ...] = (
    # (issuer code, name, jurisdiction, ISIC division, country-of-risk)
    ("ACME-CORP", "ACME Corporation", "US", "C26", "US"),
    ("EURX-AG", "EURX Industries AG", "DE", "C28", "DE"),
    ("HARBOR-GP", "Harbor Capital Partners GP", "US", "K64", "US"),
)

#: instrument code -> issuer code. These three instruments already carry positions, valuations and
#: exposure rows from the campaign, which is precisely why the backfill targets them.
_INSTRUMENT_ISSUER: dict[str, str] = {
    "EQ-ACME-US": "ACME-CORP",
    "EQ-EURX-DE": "EURX-AG",
    "PE-HARBOR-IV": "HARBOR-GP",
}


class DemoRef1Error(Exception):
    """REF-1 demo-stage refusal."""


class DemoRef1AlreadySeededError(DemoRef1Error):
    """Refuse-not-skip: the stage has already run in this tenant."""


@dataclass(frozen=True)
class Ref1Stage18Summary:
    isic_scheme_id: str
    country_scheme_id: str
    nodes_created: int
    issuers_created: int
    assignments_created: int
    instruments_backfilled: int


def run_demo_ref1_stage18(session: Session) -> Ref1Stage18Summary:
    """Seed the global taxonomy, classify the demo's first issuers, and backfill the book.

    Refuse-not-skip on re-run (the campaign discipline): a partially-seeded second pass would leave
    the demo in a state no test describes.
    """
    # Identify THIS stage's own seed exactly — family AND version. A family-only check would
    # treat any other SYSTEM ISIC scheme (a test fixture, a future revision) as this stage's work
    # and refuse to seed, leaving the demo silently unclassified.
    existing = session.execute(
        select(ClassificationScheme).where(
            ClassificationScheme.tenant_id == SYSTEM_TENANT_ID,
            ClassificationScheme.scheme_family == SCHEME_FAMILY_ISIC,
            ClassificationScheme.version_label == _ISIC_VERSION,
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise DemoRef1AlreadySeededError(
            f"the demo ISIC {_ISIC_VERSION} taxonomy is already seeded"
        )

    # --- 1. SYSTEM-tenant global taxonomy (readable by every tenant, writable by none of them) ---
    system_actor = ClassificationActor(tenant_id=SYSTEM_TENANT_ID, actor_id=DEMO_ACTOR_ID)
    isic = create_scheme(
        session,
        actor=system_actor,
        scheme_family=SCHEME_FAMILY_ISIC,
        version_label=_ISIC_VERSION,
        name="ISIC Revision 5 (demo skeleton)",
        dimension_kind=DIMENSION_KIND_SECTOR_INDUSTRY,
        authority="UNSD",
    )
    nodes = 0
    for code, name in _ISIC_SECTIONS:
        create_node(session, actor=system_actor, scheme_id=isic.id, code=code, name=name, level=1)
        nodes += 1
    for code, name, parent in _ISIC_DIVISIONS:
        create_node(
            session,
            actor=system_actor,
            scheme_id=isic.id,
            code=code,
            name=name,
            level=2,
            parent_code=parent,
        )
        nodes += 1

    countries = create_scheme(
        session,
        actor=system_actor,
        scheme_family=SCHEME_FAMILY_ISO_3166_1,
        version_label=_COUNTRY_VERSION,
        name="ISO 3166-1 alpha-2 (demo subset)",
        dimension_kind=DIMENSION_KIND_COUNTRY_OF_RISK,
        authority="ISO/UNSD M49",
    )
    for code, name in _COUNTRIES:
        create_node(
            session, actor=system_actor, scheme_id=countries.id, code=code, name=name, level=1
        )
        nodes += 1
    session.flush()

    # --- 2. The demo's FIRST issuers, under the DEMO tenant (proprietary, never SYSTEM) ---
    ref_actor = ReferenceActor(actor_id=DEMO_ACTOR_ID)
    issuer_ids: dict[str, str] = {}
    for code, name, jurisdiction, _isic_code, _country in _ISSUERS:
        core = create_legal_entity(
            session,
            tenant_id=DEMO_TENANT_ID,
            code=code,
            name=name,
            jurisdiction=jurisdiction,
            actor=ref_actor,
        )
        issuer = create_issuer(
            session,
            tenant_id=DEMO_TENANT_ID,
            legal_entity_id=core.id,
            issuer_type="CORPORATE",
            actor=ref_actor,
        )
        issuer_ids[code] = str(issuer.id)
    session.flush()

    # --- 3. Backfill issuer_id onto the instruments that already carry exposure ---
    backfilled = 0
    instrument_ids: dict[str, str] = {}
    for instrument_code, issuer_code in _INSTRUMENT_ISSUER.items():
        row = session.execute(
            select(Instrument).where(
                Instrument.tenant_id == DEMO_TENANT_ID, Instrument.code == instrument_code
            )
        ).scalar_one_or_none()
        if row is None:
            raise DemoRef1Error(
                f"demo instrument {instrument_code!r} not found — stage 18 must run AFTER the "
                f"campaign that creates the book it classifies"
            )
        instrument_ids[instrument_code] = str(row.id)
        update_instrument(session, row, actor=ref_actor, issuer_id=issuer_ids[issuer_code])
        backfilled += 1
    session.flush()

    # --- 4. Classify at INSTRUMENT grain (the ratified assignment grain) ---
    demo_actor = ClassificationActor(tenant_id=DEMO_TENANT_ID, actor_id=DEMO_ACTOR_ID)
    assignments = 0
    for instrument_code, issuer_code in _INSTRUMENT_ISSUER.items():
        _, _, _, isic_code, country = next(i for i in _ISSUERS if i[0] == issuer_code)
        capture_assignment(
            session,
            actor=demo_actor,
            entity_type="instrument",
            entity_id=instrument_ids[instrument_code],
            scheme_id=str(isic.id),
            dimension_kind=DIMENSION_KIND_SECTOR_INDUSTRY,
            node_code=isic_code,
            basis=BASIS_NOT_APPLICABLE,
        )
        assignments += 1
        capture_assignment(
            session,
            actor=demo_actor,
            entity_type="instrument",
            entity_id=instrument_ids[instrument_code],
            scheme_id=str(countries.id),
            dimension_kind=DIMENSION_KIND_COUNTRY_OF_RISK,
            node_code=country,
            # Named, not defaulted: a later reader must know WHICH convention produced this.
            basis=BASIS_IMMEDIATE_ISSUER_RESIDENCE,
        )
        assignments += 1
    session.flush()

    return Ref1Stage18Summary(
        isic_scheme_id=str(isic.id),
        country_scheme_id=str(countries.id),
        nodes_created=nodes,
        issuers_created=len(issuer_ids),
        assignments_created=assignments,
        instruments_backfilled=backfilled,
    )
