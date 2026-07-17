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
from irp_shared.demo.hg1_private import (
    DemoHg1AlreadySeededError,
    DemoHg1Error,
    DemoHg1PrereqError,
    Hg1PrivateSummary,
    run_demo_hg1_private,
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
    "DemoHg1AlreadySeededError",
    "DemoHg1Error",
    "DemoHg1PrereqError",
    "Hg1PrivateSummary",
    "run_demo_hg1_private",
    "DemoMultifamilyAlreadySeededError",
    "DemoMultifamilyError",
    "DemoMultifamilyPrereqError",
    "MultifamilyExtensionSummary",
    "demo_id",
    "run_demo_campaign",
    "run_demo_multifamily_extension",
]
