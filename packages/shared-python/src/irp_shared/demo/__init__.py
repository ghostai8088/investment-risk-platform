"""MG-1 demo validation campaign (OD-MG-1-G) + the MF-1 multi-family extension: governed runners
over the REAL service layer against the reserved DEMO tenant — distinct from (and never importing)
the synthetic seed."""

from irp_shared.demo.campaign import (
    DEMO_TENANT_ID,
    CampaignSummary,
    DemoCampaignAlreadySeededError,
    DemoCampaignError,
    demo_id,
    run_demo_campaign,
)
from irp_shared.demo.multifamily import (
    DemoMultifamilyAlreadySeededError,
    DemoMultifamilyError,
    DemoMultifamilyPrereqError,
    MultifamilyExtensionSummary,
    run_demo_multifamily_extension,
)

__all__ = [
    "DEMO_TENANT_ID",
    "CampaignSummary",
    "DemoCampaignAlreadySeededError",
    "DemoCampaignError",
    "DemoMultifamilyAlreadySeededError",
    "DemoMultifamilyError",
    "DemoMultifamilyPrereqError",
    "MultifamilyExtensionSummary",
    "demo_id",
    "run_demo_campaign",
    "run_demo_multifamily_extension",
]
