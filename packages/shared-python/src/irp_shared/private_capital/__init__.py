"""Private-capital captured inputs (CC-1): commitments, capital calls, distributions.

ENT-015 ``commitment`` (FR bitemporal) + ENT-016 ``capital_call``/``distribution`` (IA
append-only). CAPTURED INPUTS ONLY — they bind NO snapshot, NO calculation run, NO model
version (the house contract). The governed consumers (the CC-2 pacing projection) read
these rows; nothing here computes.

THE READ RULE (OD-CC-1-D): an ENT-016 event does NOT feed TWR/Dietz or backtest realized
P&L — those chains read EXCLUSIVELY ``transaction.TRANSFER_IN/TRANSFER_OUT``. A call or
distribution that also moves cash in a return-modeled book must be separately posted as a
transaction; nothing auto-bridges in v1 (the reconciliation bridge is the named v2).
"""
