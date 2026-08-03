"""Classification ORM models (REF-1, Wave-14 slice 0 — ENT-066/067/068).

The platform's first governed reference DIMENSIONS: sector/industry (one hierarchy) and
country-of-risk. Three tables in two tenancy classes, ratified at OQ-REF-1-1…30:

- ``classification_scheme`` (ENT-066, EV) + ``classification_node`` (ENT-067, EV) are the
  VOCABULARY, and both join the closed hybrid set (AD-013-R2, extending AD-013-R1's five to
  **seven**): a SYSTEM-seeded global standard taxonomy readable by every tenant, tenant-overridable
  at **node** grain. Each carries its OWN FORCE-RLS policy (migration 0056) — an unpoliced child is
  a leak (the ``calendar_holiday``/``rating_grade`` precedent).
- ``classification_assignment`` (ENT-068, **FR bitemporal**) is the ASSIGNMENT and is
  **PROPRIETARY, symmetric RLS, NEVER hybrid** — it attaches to a firm's own issuers/instruments
  (AD-013's tenant-scoped "internal classifications" clause; the OD-P1B-C MNPI argument; and,
  independently, a vendor's issuer→code mapping is per-tenant licensed content, the ``fx_rate``
  precedent).

**Why the assignment is FR and not an EV attribute column (OQ-REF-1-3, the slice's largest fork).**
Decided on drift-on-verify, which is test-proven in BOTH directions in ``test_snapshot.py``: an EV
in-place amend flips ``verify_snapshot`` to ``ok=False`` on every snapshot that pinned the record,
and that surfaces to the end user as the unfakeable ``snapshotVerified`` badge; an FR supersede
leaves the pin byte-stable because each row is an immutable VERSION. An ordinary business event —
an issuer moves sector — would therefore permanently redden the governance walk on every historical
concentration run, with **no remedy** (snapshots are IA append-only). Independently, AD-005 §2A
already classifies taxonomy ASSIGNMENTS as FR (the ENT-007 taxonomy=EV / assignments=FR split,
OD-P1B-J) — REF-1 realizes the split ENT-007 designed and deferred.

**The same criterion applied to the EV half (OQ-REF-1-3's fence).** Because the vocabulary tables
stay EV, a node correction would drift a future CON-1 pin. So the SEMANTIC node fields
(``code`` / ``parent_node_id`` / ``level``) are correctable ONLY by minting a new scheme revision;
``name``/``description`` are in-place correctable and are EXCLUDED from any pinned content hash.

**Sector and industry are ONE hierarchy, not two dimensions (OQ-REF-1-1).** Every candidate scheme
— ISIC, NACE, NAICS, and the licensed GICS/ICB alike — is a single Section→Division→Group→Class
tree. Modelling them as independent dimensions would store a derivable parent/child edge twice and
admit states the source data cannot express. A vendor delivers a LEAF code; "sector" is an ANCESTOR
of that node, resolved by ``classification.service.resolve_ancestors``.

**A revision is a NEW scheme row (OQ-REF-1-10)** — the ``model_version`` idiom. Classification
revisions reuse code strings with changed meaning and changed cardinality (NACE Rev. 2 → 2.1:
21/88 → 22/87/287/651; NAICS 2022 cut 1,057 → 1,012 six-digit codes), and inter-version
correspondence is many-to-many with PARTIAL links. A pinned historical run must resolve its code
against the version in force when it ran, which an in-place supersede could not deliver.
"""

from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from irp_shared.db.base import Base
from irp_shared.db.mixins import (
    EffectiveDatedMixin,
    FullReproducibleMixin,
    PrimaryKeyMixin,
    TenantMixin,
    TimestampMixin,
)
from irp_shared.db.types import GUID
from irp_shared.reference.models import HYBRID_TABLES
from irp_shared.temporal import TemporalClass

#: The tables REF-1 adds to the closed hybrid set (AD-013-R2), DERIVED from the single declaration
#: at ``reference.models.HYBRID_TABLES`` rather than restated. The dependency runs this way — a
#: domain package may import ``reference``, never the reverse (the reference import-direction
#: fence). Migration 0056 carries its own frozen copy for its own DDL, and the parity test proves
#: declaration == union(migrations); 0008's tuple is DDL for 0008's tables and stays byte-untouched.
HYBRID_CLASSIFICATION_TABLES: tuple[str, ...] = tuple(
    t for t in HYBRID_TABLES if t.startswith("classification_")
)

#: ``dimension_kind`` controlled vocabulary (MG-01 plain strings — new kinds are data, not a
#: migration). SECTOR_INDUSTRY is ONE hierarchical dimension (OQ-REF-1-1).
DIMENSION_KIND_SECTOR_INDUSTRY = "SECTOR_INDUSTRY"
DIMENSION_KIND_COUNTRY_OF_RISK = "COUNTRY_OF_RISK"
#: LQ-1 (ratified OQ-LQ-1-2): the liquidity tier rides this rail rather than minting a table — it is
#: a curated code assigned to an instrument on a dimension, structurally identical to sector and
#: country. **A kind added HERE and nowhere else compiles, imports and passes every census, then
#: refuses EVERY capture at runtime** — ``BASIS_BY_DIMENSION_KIND`` below is the second mandatory
#: declaration site (LQ-1 trap T4; only an EXECUTED capture reaches it).
DIMENSION_KIND_LIQUIDITY_TIER = "LIQUIDITY_TIER"
DIMENSION_KINDS: tuple[str, ...] = (
    DIMENSION_KIND_SECTOR_INDUSTRY,
    DIMENSION_KIND_COUNTRY_OF_RISK,
    DIMENSION_KIND_LIQUIDITY_TIER,
)

#: ``basis`` controlled vocabulary. NOT NULL with a sentinel for kinds that do not carry one — the
#: ``curve_type``↔``reference_key``/``REFERENCE_KEY_NONE`` precedent (OD-P2-5-K). A nullable
#: discriminator could not do the job the basis exists for: stopping two incomparable conventions
#: being silently mixed inside one concentration number.
BASIS_NOT_APPLICABLE = "NOT_APPLICABLE"
BASIS_IMMEDIATE_ISSUER_RESIDENCE = "IMMEDIATE_ISSUER_RESIDENCE"
BASIS_ULTIMATE_RISK = "ULTIMATE_RISK"
BASIS_GUARANTOR_RESIDENCE = "GUARANTOR_RESIDENCE"
BASIS_INDEX_PROVIDER_NATIONALITY = "INDEX_PROVIDER_NATIONALITY"
COUNTRY_OF_RISK_BASES: tuple[str, ...] = (
    BASIS_IMMEDIATE_ISSUER_RESIDENCE,
    BASIS_ULTIMATE_RISK,
    BASIS_GUARANTOR_RESIDENCE,
    BASIS_INDEX_PROVIDER_NATIONALITY,
)
BASES: tuple[str, ...] = (BASIS_NOT_APPLICABLE, *COUNTRY_OF_RISK_BASES)

#: The ``dimension_kind`` → admissible ``basis`` set. The binder enforces this in BOTH directions
#: (a country-of-risk row may not carry the sentinel; a sector row may carry ONLY the sentinel), so
#: the invariant cannot pass vacuously for an unlisted kind.
BASIS_BY_DIMENSION_KIND: dict[str, tuple[str, ...]] = {
    DIMENSION_KIND_SECTOR_INDUSTRY: (BASIS_NOT_APPLICABLE,),
    DIMENSION_KIND_COUNTRY_OF_RISK: COUNTRY_OF_RISK_BASES,
    # LQ-1: the sentinel ONLY. The ladder's semantics (the day thresholds) are declared on the
    # SCHEME, not carried as a basis — so a liquidity row has no convention to disambiguate. The
    # guard is NOT vacuous even at one admissible value: it is what refuses a liquidity row that
    # arrives carrying a stray COUNTRY_OF_RISK basis.
    #
    # RECORDED, NOT IMPLEMENTED: 22e-4(b)(1)(ii) permits classification at the ASSET-CLASS level as
    # well as the investment level ("portfolio investments or asset classes (as applicable)"). That
    # is a genuine future basis distinction; v1 captures investment-level only, and admitting an
    # asset-class basis is an additive value here — deliberately NOT ratified at the LQ-1 gate.
    DIMENSION_KIND_LIQUIDITY_TIER: (BASIS_NOT_APPLICABLE,),
}

#: Polymorphic assignment target (the ``identifier_xref`` P1B-3 posture: no domain FK, one
#: ``entity_type`` value written in v1). Issuer grain stays admissible later BY VALUE — no
#: migration.
ENTITY_TYPE_INSTRUMENT = "instrument"
ASSIGNMENT_ENTITY_TYPES: tuple[str, ...] = (ENTITY_TYPE_INSTRUMENT,)

#: Scheme families seeded or admitted in v1 (MG-01 plain strings).
SCHEME_FAMILY_ISIC = "ISIC"
SCHEME_FAMILY_ISO_3166_1 = "ISO_3166_1"
#: LQ-1 (ratified OQ-LQ-1-15): the liquidity ladder is the FOUR categories 17 CFR
#: 270.22e-4(b)(1)(ii)
#: NAMES — the rule supplies the vocabulary, so this is a transcription, not a design.
SCHEME_FAMILY_SEC_22E4 = "SEC_22E4"

#: The four 22e-4(b)(1)(ii) codes, IN ORDINAL ORDER (most → least liquid). Verbatim from the
#: govinfo edition ``CFR-2024-title17-vol5-sec270-22e-4.xml``: "classify each of the fund's
#: portfolio investments (including each of the fund's derivatives transactions) as a highly liquid
#: investment, moderately liquid investment, less liquid investment, or illiquid investment."
#:
#: The ordinal lives HERE as a declared tuple rather than as a column: ``classification_node.level``
#: is tree DEPTH, not severity, and the only shipped ordinal-in-a-vocabulary precedent
#: (``rating_grade.rank``) is on a different table. Nothing in LQ-1 v1 needs to compare two tiers —
#: the illiquid partition is a SINGLE named category, not a threshold on the ladder — so a column
#: would be unused weight.
TIER_HIGHLY_LIQUID = "HIGHLY_LIQUID"
TIER_MODERATELY_LIQUID = "MODERATELY_LIQUID"
TIER_LESS_LIQUID = "LESS_LIQUID"
TIER_ILLIQUID = "ILLIQUID"
LIQUIDITY_TIER_CODES: tuple[str, ...] = (
    TIER_HIGHLY_LIQUID,
    TIER_MODERATELY_LIQUID,
    TIER_LESS_LIQUID,
    TIER_ILLIQUID,
)

#: The day thresholds the rule attaches to each category, as the SCHEME's declared semantics. Held
#: as descriptive text on the seeded nodes; the platform never computes from them (the tier is a
#: captured judgment, per 22e-4(a)(8) "any investment that the fund reasonably expects…").
LIQUIDITY_TIER_SEMANTICS: dict[str, str] = {
    TIER_HIGHLY_LIQUID: (
        "convertible to cash within 3 business days without significant price impact"
    ),
    TIER_MODERATELY_LIQUID: "convertible to cash in more than 3 but 7 calendar days or less",
    TIER_LESS_LIQUID: "saleable within 7 calendar days but settlement expected to take longer",
    TIER_ILLIQUID: (
        "not saleable within 7 calendar days without significantly changing market value"
    ),
}


class ClassificationScheme(PrimaryKeyMixin, TenantMixin, EffectiveDatedMixin, TimestampMixin, Base):
    """A classification taxonomy at a specific authority VERSION (ENT-066, EV, hybrid).

    Keyed ``(tenant_id, scheme_family, version_label)`` — a revision is a NEW row (OQ-REF-1-10),
    with ``version_label`` storing the authority's own string verbatim ("Rev. 5", "Rev. 2.1",
    "2022"). Assignments FK the scheme VERSION, never the family.

    Countries ride this same shape as an ``ISO_3166_1`` scheme rather than a fourth table
    (OQ-REF-1-7); node ``code`` is the ISO 3166-1 **alpha-2** value. Alpha-3 and UN M49 numeric are
    deliberately NOT stored in v1 — the ``currency`` precedent carries ``numeric_code`` because
    ISO-4217 numeric has payment consumers and we have none. Recorded deferral; trigger: the first
    consumer requiring alpha-3 (e.g. a regulatory report).
    """

    __tablename__ = "classification_scheme"
    __temporal_class__ = TemporalClass.EFFECTIVE_DATED
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "scheme_family",
            "version_label",
            name="uq_classification_scheme_tenant_family_version",
        ),
    )

    scheme_family: Mapped[str] = mapped_column(String(50), nullable=False)  # ISIC/NACE/ISO_3166_1
    version_label: Mapped[str] = mapped_column(String(50), nullable=False)  # the authority's string
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    authority: Mapped[str | None] = mapped_column(String(100), nullable=True)  # UNSD/Eurostat/...
    #: Which ``dimension_kind`` this scheme's nodes classify. A scheme serves exactly one dimension.
    dimension_kind: Mapped[str] = mapped_column(String(30), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    record_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class ClassificationNode(PrimaryKeyMixin, TenantMixin, EffectiveDatedMixin, TimestampMixin, Base):
    """One code within a scheme, at a level, under a parent (ENT-067, EV, hybrid, own policy).

    ``UNIQUE(tenant_id, scheme_id, code)`` with a **plain** parent self-FK — deliberately NOT
    constrained intra-tenant (OQ-REF-1-2). The ``rating_grade``/``calendar_holiday`` precedent is
    exactly this: a plain parent FK plus tenant-qualified uniqueness is what lets a tenant row hang
    off the SYSTEM parent its RLS ``USING`` already admits. An intra-tenant parent constraint would
    force a tenant overriding one leaf to duplicate every ancestor up to the root, which is not the
    shadow-one-row override AD-013-R1 specifies.

    ``level`` is the ordinal depth (1 = the scheme's top level). Cycle, same-scheme-parent and
    level-monotonicity are binder-enforced with negative controls — an adjacency table without
    those guards admits a cycle that would hang the ancestor walk.
    """

    __tablename__ = "classification_node"
    __temporal_class__ = TemporalClass.EFFECTIVE_DATED
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "scheme_id", "code", name="uq_classification_node_tenant_scheme_code"
        ),
    )

    scheme_id: Mapped[str] = mapped_column(
        GUID, ForeignKey("classification_scheme.id"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    #: Ordinal depth, 1 = top level. Semantic: correctable only by a new scheme revision.
    level: Mapped[int] = mapped_column(Integer, nullable=False)
    parent_node_id: Mapped[str | None] = mapped_column(
        GUID, ForeignKey("classification_node.id"), nullable=True, index=True
    )
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    record_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class ClassificationAssignment(
    PrimaryKeyMixin, TenantMixin, FullReproducibleMixin, TimestampMixin, Base
):
    """An entity carries a code, from a scheme, on a dimension (ENT-068, **FR bitemporal**).

    PROPRIETARY symmetric RLS — never hybrid. Polymorphic ``(entity_type, entity_id)`` target with
    REF-1 writing ``entity_type='instrument'`` ONLY (the ``identifier_xref`` posture): no domain FK,
    so issuer grain is admissible later by value with no migration.

    **Grain rationale, corrected at the gate (OQ-REF-1-5).** The draft argued instrument grain
    avoids forcing CON-1 to mint an instrument→issuer pin. That differential is ZERO: REQ-CRD-003's
    acceptance is literally "per issuer/sector", ``exposure_aggregate`` has no issuer column, and
    ``update_instrument`` mutates ``issuer_id`` IN PLACE with only a ``record_version`` bump and no
    version row — so CON-1 must pin that edge under EITHER grain. What instrument grain genuinely
    buys is removing the unpinned hop from the SECTOR and COUNTRY axes. **Named CON-1 carry:** CON-1
    must either mint an instrument→issuer component kind (EV-flavored, drift-prone) or refuse the
    per-issuer half of REQ-CRD-003 — ``instrument`` being unpinned is an AD-014 exposure for CON-1,
    not a safety property.

    Current head ``(tenant_id, entity_type, entity_id, scheme_id, dimension_kind) WHERE valid_to IS
    NULL AND system_to IS NULL`` (OQ-REF-1-8). ``scheme_id`` participates deliberately: one
    instrument may legitimately carry an ISIC sector AND a NACE sector at once. The stated
    consequence is that a scheme REVISION leaves two open assignments in one family until every
    assignment is re-captured, so **mixed-version aggregation is a legal state that reads and CON-1
    must refuse fail-closed** rather than silently blend two code spaces.

    ``node_code`` is denormalized text, not an FK: the capture binder resolves ``(scheme_id,
    node_code)`` against ``classification_node`` fail-closed BEFORE insert (OQ-REF-1-20). A DB FK
    alone would be wrong here — PostgreSQL referential checks bypass RLS, so an FK would let a
    tenant bind a node its own ``USING`` cannot see.
    """

    __tablename__ = "classification_assignment"
    __temporal_class__ = TemporalClass.FULL_REPRODUCIBLE
    __table_args__ = (
        Index(
            "uq_classification_assignment_current",
            "tenant_id",
            "entity_type",
            "entity_id",
            "scheme_id",
            "dimension_kind",
            unique=True,
            postgresql_where=text("valid_to IS NULL AND system_to IS NULL"),
            sqlite_where=text("valid_to IS NULL AND system_to IS NULL"),
        ),
    )

    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[str] = mapped_column(GUID, nullable=False, index=True)
    scheme_id: Mapped[str] = mapped_column(
        GUID, ForeignKey("classification_scheme.id"), nullable=False, index=True
    )
    dimension_kind: Mapped[str] = mapped_column(String(30), nullable=False)
    #: The assigned node's code, resolved fail-closed against the scheme at capture.
    node_code: Mapped[str] = mapped_column(String(50), nullable=False)
    #: NOT NULL with the ``NOT_APPLICABLE`` sentinel; binder-enforced against ``dimension_kind``.
    basis: Mapped[str] = mapped_column(String(40), nullable=False, default=BASIS_NOT_APPLICABLE)
    restatement_reason: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )  # set ONLY on a correction (TR-08)
    # Explicitly named: the NAMING_CONVENTION default
    # (fk_<table>_<col>_<referred_table>) would be 68 chars and PostgreSQL truncates identifiers at
    # 63 — found by the P4 executed dry run, not by reading.
    supersedes_id: Mapped[str | None] = mapped_column(
        GUID,
        ForeignKey(
            "classification_assignment.id", name="fk_classification_assignment_supersedes_id"
        ),
        nullable=True,
    )
    record_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


# NOTE: classification_assignment (FR, ENT-068) is NOT append-only — the FR protocol requires
# close-out UPDATEs (the proxy_mapping/factor_return precedent). Content-immutability of a closed
# version is service-enforced + tested.
