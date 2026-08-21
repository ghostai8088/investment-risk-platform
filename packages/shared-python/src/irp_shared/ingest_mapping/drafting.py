"""The drafting model, registered like every other model on this platform (W19-S3a).

INGEST-1 adopted this without a fork: *the AI is a REGISTERED MODEL.* Every proposal records which
model, which version, and which prompt produced it. It costs something — AI drafting enters model
governance with the review burden that implies — and the alternative is an ungoverned model
influencing what the data MEANS, inside a platform whose entire claim is that nothing is ungoverned.

**Per-tenant, and the SYSTEM path is ruled out.** ``model``/``model_version`` are tenant-scoped and
PROPRIETARY; they sit outside the closed seven-table hybrid set, so a single platform-wide drafting
model is not available and was not sought. Each tenant registers its own head.

**What is NOT here.** No model call. The drafting act runs OPERATOR-SIDE and sees schema only
(OQ-ING-3=A); this module registers the *identity* a proposal is attributed to. The committed
artifacts of the demonstrating act live under ``08_testing_qa/ingest_mapping_proposal/``.
"""

from __future__ import annotations

import hashlib

from sqlalchemy.orm import Session

from irp_shared.model.models import Model, ModelVersion
from irp_shared.model.service import (
    ModelVersionConflictError,
    WrongModelVersionError,
    register_model_version,
    resolve_or_register_model,
    resolve_or_register_version,
)

#: The model inventory head. `AI_ML` is the shipped `model_type` vocabulary value for this class.
DRAFTER_MODEL_CODE = "INGEST-MAPPING-DRAFTER"
DRAFTER_MODEL_NAME = "Ingest mapping drafter"
DRAFTER_MODEL_TYPE = "AI_ML"

#: The version label IS the model identity. A different model is a different version, by
#: construction, so a proposal can never be attributed to "the drafter" in the abstract.
DRAFTER_VERSION_LABEL = "claude-opus-5"

#: The drafting PROTOCOL version — the prompt contract and the closed vocabulary it names. Bumping
#: the vocabulary bumps this, because a proposal drafted against a different operation set is not
#: comparable to one drafted against this one.
DRAFTER_CODE_VERSION = "v1"

#: Written BEFORE this constant was named: `test_methodology_refs.py` fails on any
#: `*_METHODOLOGY_REF` that is not an existing path under `05_analytics_methodologies/`.
DRAFTER_METHODOLOGY_REF = "05_analytics_methodologies/ingest_mapping_drafting_v1.md"

#: The assumptions this model version registers under. Asserted by exact set equality after
#: resolution, so a peer registered with different assumptions is caught rather than reused.
DRAFTER_ASSUMPTIONS: tuple[str, ...] = (
    "The model sees SCHEMA ONLY: column names, inferred types, and shape-preserving obfuscated "
    "samples. It never sees a client holding.",
    "The model PROPOSES; a human RATIFIES; the platform executes the ratified version. The model "
    "is never in the path of a number.",
    "Proposals are drawn from a CLOSED operation vocabulary. A file the vocabulary cannot express "
    "is refused by name rather than approximated.",
    "The drafting act runs operator-side, outside the deployed product. No external model call "
    "happens inside the deployed stack and no API key exists there.",
)

DRAFTER_LIMITATIONS: tuple[str, ...] = (
    "No accuracy claim is made or measured. A proposal is a draft; correctness is established by "
    "the ratifying human and by the interpreter's refusals, not by a score.",
    "Recorded provenance proves PRESENCE, not ORIGIN: a real model version, a real prompt whose "
    "hash matches, and the response it produced. Provider-signed attestation does not exist today.",
    "A date format proposed from an obfuscated sample is an ASSUMPTION. Day-first and month-first "
    "are indistinguishable in an obfuscated sample and differ silently for most of every month.",
    "The model may only be REGISTERED by an agent actor — validation and tiering refuse a "
    "non-human actor by mechanism (BR-15/MG-07).",
)


def prompt_identity(prompt_bytes: bytes) -> str:
    """The sha256 a proposal records, so its prompt is checkable rather than asserted."""
    return hashlib.sha256(prompt_bytes).hexdigest()


def register_drafting_model(
    session: Session,
    *,
    tenant_id: str,
    actor_id: str,
    actor_type: str = "user",
) -> tuple[Model, ModelVersion]:
    """Resolve-or-register this tenant's drafting model head and version, idempotently.

    The post-checks after ``resolve_or_register_version`` are **not decoration**: they are the only
    thing that catches a squatted or ``code_version``-mismatched peer on the race path and on
    idempotent re-invocation, and copying the registrar without them reproduces the P3-C1
    register/run-consistency defect.

    ``status="REGISTERED"`` is passed explicitly. Omitting it mints ``status=None``, which binds
    NOWHERE — ``assert_model_version_of`` raises ``UnregisteredModelError`` rather than a status
    error, and the version is unusable in a way nothing at registration time complains about. That
    is the trap ``POST /models`` still sits in, so it is spelled out here rather than inherited.
    """
    model = resolve_or_register_model(
        session,
        tenant_id=str(tenant_id),
        code=DRAFTER_MODEL_CODE,
        name=DRAFTER_MODEL_NAME,
        model_type=DRAFTER_MODEL_TYPE,
        actor_id=str(actor_id),
        description=(
            "Drafts a proposed source mapping from a file's SCHEMA. Proposes only; a human "
            "ratifies; the platform executes the ratified version."
        ),
        actor_type=actor_type,
    )
    version = resolve_or_register_version(
        session,
        model=model,
        version_label=DRAFTER_VERSION_LABEL,
        register=lambda: register_model_version(
            session,
            model=model,
            version_label=DRAFTER_VERSION_LABEL,
            actor_id=str(actor_id),
            methodology_ref=DRAFTER_METHODOLOGY_REF,
            code_version=DRAFTER_CODE_VERSION,
            status="REGISTERED",
            assumptions=list(DRAFTER_ASSUMPTIONS),
            limitations=list(DRAFTER_LIMITATIONS),
            actor_type=actor_type,
        ),
    )
    if version.status != "REGISTERED":
        # An UNREGISTERED version binds NOWHERE, and the failure is silent at registration time.
        raise WrongModelVersionError(str(version.id), DRAFTER_MODEL_CODE)
    if version.code_version != DRAFTER_CODE_VERSION:
        # A peer already exists under this version_label with a DIFFERENT protocol version — the
        # immutable inventory identity cannot be silently re-pointed.
        raise ModelVersionConflictError(
            DRAFTER_MODEL_CODE, DRAFTER_VERSION_LABEL, DRAFTER_CODE_VERSION
        )
    return model, version
