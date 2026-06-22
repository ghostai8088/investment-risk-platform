"""Model registry skeleton (P1A-2, REQ-MDG-001 / DEP-MREG).

The inventory of models and immutable versions (MG-01/MG-02, BR-3): ``register_model`` /
``register_model_version`` capture a model + version (+ assumptions/limitations), and
``assert_registered_model_version`` is the inventory-before-use gate. Generic and domain-agnostic
— ``model_type`` is a controlled-vocabulary string, so market/credit/liquidity/scenario/
private-asset-proxy/AI-ML families register by value, never a schema change. Governance fields
(tier/validation_status/approved_use/owner/developer) are **non-enforcing placeholders** reserved
for the P7 validation/approval workflow; P1A-2 enforces no tiering, validation, or approval.
"""
