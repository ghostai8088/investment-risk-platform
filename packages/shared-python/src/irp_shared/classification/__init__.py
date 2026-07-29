"""Governed classification dimensions (REF-1, Wave-14 slice 0 — ENT-066/067/068).

Hosts the vocabulary (``classification_scheme`` / ``classification_node``, EV + hybrid) and the
FR bitemporal ``classification_assignment`` capture rail. This is a NEW package by necessity: the
rail cannot live in ``reference/`` (allowlist-fenced, and it runs no DQ gate at all) nor in
``marketdata/``, and ``ingestion/`` is fenced against domain packages.
"""
