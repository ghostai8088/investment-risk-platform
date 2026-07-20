"""Governed commitment-pacing projection (CC-2, ENT-059) — the SEVENTEENTH governed number.

The deterministic Takahashi-Alexander pacing recursion (JPM 28(2):90-100, 2002) projects a
private-fund commitment's future capital calls, distributions, and NAV from the CC-1 captured
substrate (commitment + calls + distributions + the latest valuation mark). NO optimizer, NO
randomness — a closed-form deterministic linear system. The five model inputs (rate-of-contribution
schedule, fund life, bow, growth, yield floor) are DECLARED per-version parameters; only the
FUNCTIONAL FORM is Takahashi-Alexander's (no constant is minted from the paper). See
``05_analytics_methodologies/pacing_commitment_projection_v1.md``.
"""
