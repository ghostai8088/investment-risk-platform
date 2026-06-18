# Shared Python library (`irp-shared`)

Cross-cutting Python utilities shared across backend and worker. **Scaffold only.**

Currently exposes:
- `__version__`
- `TemporalClass` — the ratified FR/IA/EV temporal classes (AD-005 / BR-19), so future entities can declare their class.

No persistence, no domain logic.
