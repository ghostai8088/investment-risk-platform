"""Refusals minted by the INGEST-1 mapping spine (W19-S3a, REQ-INT-001 clauses 1/5/6/10).

**Every class here has a test that makes it FIRE (P9), and each firing test carries a POSITIVE
control proving the input that should trigger it actually arrived (P18 clause 1).** The reason this
docstring says so rather than a plan saying so: this project has shipped structurally UNFIREABLE
refusals twice — CON-1's mixed-VERSION refusal, and again in the Wave-19 ratification commit — and
both times the design document named the refusal without naming what reaches it. The firing
condition for each is in the class docstring.

**That claim is now MECHANICAL, and it was not when this module first shipped.** The original
docstring said a census asserted it; no such census existed, in this module or anywhere — the slice
review caught the claim and it was a false governance record of exactly the class this module's own
prose accuses two earlier incidents of. The census is
``test_ingest_mapping.py::test_every_declared_refusal_is_fired_by_a_test``: it walks
``MappingError.__subclasses__()`` recursively and requires every class to be named by a test that
raises it, with a floor so the population cannot collapse silently. It is also P9's mechanical limb,
which this repo did not have.

P9's corollary, and the reason "the refusal exists in the source" is never evidence: *a refusal that
cannot fire and a refusal that never fires are indistinguishable from the diff.*
"""

from __future__ import annotations


class MappingError(Exception):
    """Base for every mapping-spine refusal, so a caller can fail closed on the family."""


class MappingNotVisible(MappingError):
    """A mapping version id resolves to no row in the acting tenant (RLS + explicit predicate).

    FIRES WHEN: a load or ratify names a mapping id belonging to another tenant, or no row at all.
    """

    def __init__(self, mapping_version_id: str) -> None:
        super().__init__(f"mapping version {mapping_version_id} is not visible in this tenant")
        self.mapping_version_id = mapping_version_id


class UnratifiedMappingError(MappingError):
    """No RATIFIED mapping version exists for the (data_source, source_type) a load names.

    FIRES WHEN: a positions file is loaded against a source whose only versions are PROPOSED,
    SUPERSEDED or WITHDRAWN — or which has none at all. REQ-INT-001 clause (1).
    """

    def __init__(self, data_source_id: str, source_type: str) -> None:
        super().__init__(
            f"no RATIFIED mapping version for data_source={data_source_id} "
            f"source_type={source_type}; a file loads ONLY through a ratified mapping"
        )
        self.data_source_id = data_source_id
        self.source_type = source_type


class UnsupportedOperationError(MappingError):
    """An operation outside the closed set (OQ-ING-2=A).

    FIRES WHEN: ``operations[i]["op"]`` is not one of the seven. **The message NAMES the offending
    operation verbatim** — the ratified decision requires the refusal to name the unsupported
    operation rather than fail vaguely, so a file that cannot be expressed forces a NEW operation to
    be added deliberately and reviewed. Asserted on the MESSAGE, not the exception type.
    """

    def __init__(self, op: str, supported: tuple[str, ...]) -> None:
        super().__init__(
            f"unsupported mapping operation {op!r}; the closed set is {', '.join(supported)}"
        )
        self.op = op


class UnknownTargetFieldError(MappingError):
    """An operation targets a canonical field outside the declared target set.

    FIRES WHEN: ``operations[i]["target"]`` is anything but a member of
    ``interpreter.TARGET_FIELDS`` — e.g. a mapping trying to write ``market_value``, a column
    ``position`` deliberately does not have.
    """

    def __init__(self, target: str, allowed: tuple[str, ...]) -> None:
        super().__init__(
            f"unknown canonical target field {target!r}; the declared set is {', '.join(allowed)}"
        )
        self.target = target


class MissingSourceColumnError(MappingError):
    """A declared source column is absent from the staged row's payload keys.

    FIRES WHEN: the ratified mapping names ``SOURCE_COL`` and the staged payload has no such key —
    the shape a file whose header drifted produces. Fails the batch closed rather than writing a
    null holding.
    """

    def __init__(self, column: str, row_number: int) -> None:
        super().__init__(f"staged row {row_number} has no source column {column!r}")
        self.column = column
        self.row_number = row_number


class CastRefusedError(MappingError):
    """A value is not castable to the declared type.

    FIRES WHEN: ``cast`` is asked for ``decimal`` and the cell holds ``"n/a"`` (or any non-numeric),
    or for ``integer`` and the cell holds a fraction. Never coerced, never defaulted to zero.
    """

    def __init__(self, value: object, to_type: str, row_number: int) -> None:
        super().__init__(f"staged row {row_number}: cannot cast {value!r} to {to_type}")
        self.value = value
        self.to_type = to_type
        self.row_number = row_number


class DateParseRefusedError(MappingError):
    """A value does not parse under the declared format.

    FIRES WHEN: ``parse-date`` declares ``%d/%m/%Y`` and the cell holds ``"31/02/2026"`` (a real
    calendar refusal, not a shape refusal) or ``"2026-08-20"`` (the right date in the wrong format).
    The format is DECLARED by the mapping, never sniffed — sniffing is how a UK file silently loads
    as a US one.
    """

    def __init__(self, value: object, fmt: str, row_number: int) -> None:
        super().__init__(
            f"staged row {row_number}: {value!r} does not parse under declared format {fmt!r}"
        )
        self.value = value
        self.fmt = fmt
        self.row_number = row_number


class ScaleRefusedError(MappingError):
    """A scale operation cannot be applied.

    FIRES WHEN: the input is non-numeric, **or** the mapping's declared ``factor`` is zero, negative
    or non-finite. The factor arm matters: a zero factor silently turns a whole book into zero
    holdings and every downstream reproduction of that load would agree with itself.
    """

    def __init__(self, reason: str, row_number: int | None = None) -> None:
        where = "" if row_number is None else f"staged row {row_number}: "
        super().__init__(f"{where}scale refused: {reason}")
        self.reason = reason
        self.row_number = row_number


class ConcatenateRefusedError(MappingError):
    """A concatenate operation is missing one of its named inputs.

    FIRES WHEN: ``concatenate`` names ``["EXCHANGE", "LOCAL_CODE"]`` and the staged payload carries
    only one of them. Distinct from ``MissingSourceColumnError`` because the partial result is the
    dangerous case — half an identifier looks like a valid identifier.
    """

    def __init__(self, missing: tuple[str, ...], row_number: int) -> None:
        super().__init__(
            f"staged row {row_number}: concatenate is missing input column(s) "
            f"{', '.join(missing)}"
        )
        self.missing = missing
        self.row_number = row_number


class ConstantTypeRefusedError(MappingError):
    """A declared constant is not coercible to its target field's type.

    FIRES WHEN: a mapping declares ``{"op": "constant", "target": "quantity", "value": "SHARES"}``
    — a string literal onto a Decimal field. The refusal is at RATIFICATION as well as at load, so a
    mapping carrying it can never become the ratified one.
    """

    def __init__(self, value: object, target: str) -> None:
        super().__init__(
            f"constant {value!r} is not coercible to the type of target field {target!r}"
        )
        self.value = value
        self.target = target


class CodeLookupRefusedError(MappingError):
    """A code-lookup resolves to nothing, or ambiguously, as of the load.

    FIRES WHEN: (a) the identifier value has no ``identifier_xref`` row open at the batch's
    ``lookup_as_of``; or (b) it resolves ambiguously (``AmbiguousIdentifier``). Both arms fire in
    tests. Never interpolated, never carried forward, never "closest match".
    """

    def __init__(self, scheme: str, value: object, row_number: int, reason: str) -> None:
        super().__init__(
            f"staged row {row_number}: code-lookup {scheme}={value!r} {reason} as of the load"
        )
        self.scheme = scheme
        self.value = value
        self.row_number = row_number
        self.reason = reason


class OverlappingLoadError(MappingError):
    """An overlapping re-load that is not flagged a restatement (DP-19-7, fail-closed).

    FIRES WHEN: the loaded row's ``(portfolio, instrument)`` already has an OPEN current-head
    position version at the same ``valid_from`` and the load did not set ``restatement_reason``.
    A flagged restatement supersedes bitemporally through ``correct_position``; an unflagged one is
    refused, because silently overwriting a client's holdings is the failure this platform is
    supposed to make impossible.
    """

    def __init__(self, portfolio_id: str, instrument_id: str, row_number: int) -> None:
        super().__init__(
            f"staged row {row_number}: an open position already exists for portfolio "
            f"{portfolio_id} / instrument {instrument_id} at this valid_from; flag the load a "
            f"restatement to supersede it"
        )
        self.portfolio_id = portfolio_id
        self.instrument_id = instrument_id
        self.row_number = row_number


class SelfRatificationError(MappingError):
    """The ratifier is the proposer (REQ-INT-001 clause 6, the refusal half).

    FIRES WHEN: ``ratify_mapping_version`` is called with an actor equal to the version's
    ``proposed_by_actor_id``. **This is the refusal half of four-eyes only.** The permission
    separation — a ratifier code never co-granted with the proposer path, with its P11 holder-set
    pin, route census and SoD row — lands at S3b, and *that* is what makes four-eyes real. Shipping
    the equality check here was ratified as a deliberate widening of S3a's scope line (DS3a-3),
    not taken as a builder's call.
    """

    def __init__(self, actor_id: str) -> None:
        super().__init__(f"actor {actor_id} proposed this mapping version and may not ratify it")
        self.actor_id = actor_id


class MappingContentImmutableError(MappingError):
    """An attempt to edit a mapping version's CONTENT in place.

    FIRES WHEN: any update touches a column outside ``models.LIFECYCLE_FIELDS``. Content
    immutability on this table is service-enforced, NOT trigger-enforced (the row must stay
    status-mutable), so this refusal is the only thing standing between a ratified mapping and a
    silent re-point. An edit is a NEW version that supersedes.
    """

    def __init__(self, fields: tuple[str, ...]) -> None:
        super().__init__(
            f"mapping version content is immutable; an edit mints a NEW version. "
            f"Refused fields: {', '.join(fields)}"
        )
        self.fields = fields


class MappingLifecycleError(MappingError):
    """An illegal lifecycle transition.

    FIRES WHEN: ratifying a version that is not PROPOSED — already RATIFIED, or SUPERSEDED. A gate
    that fires only in the obvious state is not a control until the alternate paths are closed (the
    Wave-11 standing review angle).

    ``WITHDRAWN`` is deliberately NOT named here even though the vocabulary declares it: no verb
    transitions a version into that state, so naming it as a firing condition would describe
    behaviour the shipped code cannot produce. The constant is RESERVED; the withdraw verb is
    S3b's, with the rest of the lifecycle.
    """

    def __init__(self, mapping_version_id: str, status: str, attempted: str) -> None:
        super().__init__(f"mapping version {mapping_version_id} is {status}; cannot {attempted}")
        self.mapping_version_id = mapping_version_id
        self.status = status
        self.attempted = attempted


class IncoherentTargetOperationError(MappingError):
    """An operation cannot produce the type its target requires.

    FIRES WHEN: a mapping aims ``rename``, ``concatenate`` or ``code-lookup`` at ``quantity`` or
    ``cost_basis``, or aims anything but ``parse-date`` at ``valid_from``. Refused at PROPOSAL, so
    the incoherent mapping never reaches a human for ratification.

    **This exists because the slice review reproduced its absence end to end**: a `rename` into
    `quantity` passed the coherence check, was proposed and RATIFIED through the real service
    verbs, and then raised a bare ``decimal.InvalidOperation`` at load — an ``ArithmeticError``,
    not a ``MappingError``, so a caller failing closed on the family caught nothing. The trigger
    value was ``1,234.50``: an ordinary comma-formatted number, structurally identical to the
    demonstrating file's own book-cost column.
    """

    def __init__(self, op: str, target: str, allowed: tuple[str, ...]) -> None:
        super().__init__(
            f"operation {op!r} cannot produce a value for target {target!r}; "
            f"that target admits {', '.join(allowed)}"
        )
        self.op = op
        self.target = target
        self.allowed = allowed


class QuantityUnitTooLongError(MappingError):
    """A quantity unit is longer than the column that stores it.

    FIRES WHEN: an interpreted ``quantity_unit`` exceeds ``position.quantity_unit``'s 20 characters
    — e.g. ``"SHARES (POST-SPLIT ADJ)"``.

    Refused rather than TRUNCATED, and the difference is the whole point: cutting that value to
    ``"SHARES (POST-SPLIT A"`` writes a governed record saying something the client's file did not
    say, with nothing downstream able to tell it was altered. A refused batch is recoverable; a
    quietly rewritten holding is not. The first draft of the interpreter truncated silently.
    """

    def __init__(self, value: str, limit: int, row_number: int) -> None:
        super().__init__(
            f"staged row {row_number}: quantity unit {value!r} is {len(value)} characters and the "
            f"column holds {limit} — refused rather than truncated"
        )
        self.value = value
        self.limit = limit
        self.row_number = row_number


class PortfolioCodeNotVisible(MappingError):
    """A portfolio code in a staged row resolves to no node in the acting tenant.

    FIRES WHEN: the file's ``Account Ref`` (or whatever column the mapping routes to
    ``portfolio_code``) names a node this tenant does not have — including one that belongs to
    another tenant.

    Its own class rather than ``MappingNotVisible``, because that error stores its argument as
    ``mapping_version_id`` and a handler reading that attribute to report "which mapping was not
    visible" would have been handed a portfolio code. A record that mislabels what failed to
    resolve is a small false record, and small false records are how the large ones start.
    """

    def __init__(self, code: str) -> None:
        super().__init__(f"portfolio code {code!r} is not visible in this tenant")
        self.code = code
