"""Worker entrypoint (scaffold).

Placeholder for the future calculation-run worker (AD-006). It performs no calculations.
When implemented, every run MUST produce a CalculationRun record binding code/model
version, input snapshot, assumption set, RNG seed, initiator and timestamps, and MUST NOT
bypass the audit (BR-12) or lineage (BR-13) frameworks.
"""

from __future__ import annotations


def run_once() -> dict[str, str]:
    """Placeholder heartbeat used to prove worker wiring."""
    return {"status": "idle", "component": "worker"}


def main() -> None:  # pragma: no cover - thin entrypoint
    result = run_once()
    print(f"irp-worker: {result['status']}")


if __name__ == "__main__":  # pragma: no cover
    main()
