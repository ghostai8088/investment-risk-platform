"""MG-1 demo validation campaign (OD-MG-1-G): a governed runner over the REAL service layer
against the reserved DEMO tenant — distinct from (and never importing) the synthetic seed."""

from irp_shared.demo.campaign import (
    DEMO_TENANT_ID,
    CampaignSummary,
    DemoCampaignAlreadySeededError,
    DemoCampaignError,
    demo_id,
    run_demo_campaign,
)

__all__ = [
    "DEMO_TENANT_ID",
    "CampaignSummary",
    "DemoCampaignAlreadySeededError",
    "DemoCampaignError",
    "demo_id",
    "run_demo_campaign",
]
