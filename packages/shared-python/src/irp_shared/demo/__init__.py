"""MG-1 demo validation campaign (OD-MG-1-G) + the MF-1 multi-family extension: governed runners
over the REAL service layer against the reserved DEMO tenant — distinct from (and never importing)
the synthetic seed."""

from irp_shared.demo.bt3_stage7 import (
    Bt3Stage7Summary,
    DemoBt3AlreadySeededError,
    DemoBt3PrereqError,
    run_demo_bt3_stage7,
)
from irp_shared.demo.campaign import (
    DEMO_TENANT_ID,
    CampaignSummary,
    DemoCampaignAlreadySeededError,
    DemoCampaignError,
    demo_id,
    run_demo_campaign,
)
from irp_shared.demo.cc1_stage8 import (
    Cc1Stage8Summary,
    DemoCc1AlreadySeededError,
    DemoCc1Error,
    DemoCc1PrereqError,
    run_demo_cc1_stage8,
)
from irp_shared.demo.cc2_stage9 import (
    Cc2Stage9Summary,
    DemoCc2AlreadySeededError,
    DemoCc2Error,
    DemoCc2PrereqError,
    run_demo_cc2_stage9,
)
from irp_shared.demo.ds2_stage6 import (
    DemoDs2AlreadySeededError,
    DemoDs2Error,
    DemoDs2PrereqError,
    Ds2Stage6Summary,
    run_demo_ds2_stage6,
)
from irp_shared.demo.eshs_stage4 import (
    DemoEshsAlreadySeededError,
    DemoEshsError,
    DemoEshsPrereqError,
    EshsStage4Summary,
    run_demo_eshs_stage4,
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
from irp_shared.demo.ppf1_stage11 import (
    DemoPpf1AlreadySeededError,
    DemoPpf1Error,
    DemoPpf1PrereqError,
    Ppf1Stage11Summary,
    run_demo_ppf1_stage11,
)
from irp_shared.demo.ppf2_stage12 import (
    DemoPpf2AlreadySeededError,
    DemoPpf2Error,
    DemoPpf2PrereqError,
    Ppf2Stage12Summary,
    run_demo_ppf2_stage12,
)
from irp_shared.demo.ppf3_stage13 import (
    DemoPpf3AlreadySeededError,
    DemoPpf3Error,
    DemoPpf3PrereqError,
    Ppf3Stage13Summary,
    run_demo_ppf3_stage13,
)
from irp_shared.demo.rs1_stage5 import (
    DemoRs1AlreadySeededError,
    DemoRs1Error,
    DemoRs1PrereqError,
    Rs1Stage5Summary,
    run_demo_rs1_stage5,
)
from irp_shared.demo.stage10_api1 import (
    DemoStage10AlreadySeededError,
    DemoStage10Error,
    DemoStage10PrereqError,
    Stage10Api1Summary,
    run_demo_stage10_api1,
)

__all__ = [
    "DEMO_TENANT_ID",
    "CampaignSummary",
    "DemoCampaignAlreadySeededError",
    "DemoCampaignError",
    "DemoDs2AlreadySeededError",
    "DemoDs2Error",
    "DemoDs2PrereqError",
    "Ds2Stage6Summary",
    "DemoEshsAlreadySeededError",
    "DemoEshsError",
    "DemoEshsPrereqError",
    "EshsStage4Summary",
    "Bt3Stage7Summary",
    "DemoBt3AlreadySeededError",
    "DemoBt3PrereqError",
    "Cc1Stage8Summary",
    "DemoCc1AlreadySeededError",
    "DemoCc1Error",
    "DemoCc1PrereqError",
    "Cc2Stage9Summary",
    "DemoCc2AlreadySeededError",
    "DemoCc2Error",
    "DemoCc2PrereqError",
    "run_demo_bt3_stage7",
    "run_demo_cc1_stage8",
    "run_demo_cc2_stage9",
    "run_demo_ds2_stage6",
    "run_demo_eshs_stage4",
    "DemoHg1AlreadySeededError",
    "DemoHg1Error",
    "DemoHg1PrereqError",
    "Hg1PrivateSummary",
    "run_demo_hg1_private",
    "DemoMultifamilyAlreadySeededError",
    "DemoMultifamilyError",
    "DemoMultifamilyPrereqError",
    "DemoRs1AlreadySeededError",
    "DemoRs1Error",
    "DemoRs1PrereqError",
    "MultifamilyExtensionSummary",
    "Rs1Stage5Summary",
    "demo_id",
    "run_demo_campaign",
    "run_demo_multifamily_extension",
    "run_demo_rs1_stage5",
    "DemoStage10AlreadySeededError",
    "DemoStage10Error",
    "DemoStage10PrereqError",
    "Stage10Api1Summary",
    "run_demo_stage10_api1",
    "DemoPpf1AlreadySeededError",
    "DemoPpf1Error",
    "DemoPpf1PrereqError",
    "DemoPpf2AlreadySeededError",
    "DemoPpf2Error",
    "DemoPpf2PrereqError",
    "Ppf2Stage12Summary",
    "run_demo_ppf2_stage12",
    "DemoPpf3AlreadySeededError",
    "DemoPpf3Error",
    "DemoPpf3PrereqError",
    "Ppf3Stage13Summary",
    "run_demo_ppf3_stage13",
    "Ppf1Stage11Summary",
    "run_demo_ppf1_stage11",
]
