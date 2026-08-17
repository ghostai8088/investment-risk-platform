"""MG-1 demo validation campaign (OD-MG-1-G) + the MF-1 multi-family extension: governed runners
over the REAL service layer against the reserved DEMO tenant — distinct from (and never importing)
the synthetic seed."""

from irp_shared.demo.bt3_stage7 import (
    Bt3Stage7Summary,
    DemoBt3AlreadySeededError,
    DemoBt3PrereqError,
    run_demo_bt3_stage7,
)
from irp_shared.demo.cal1b_stage21 import (
    Cal1bStage21Summary,
    DemoCal1bAlreadySeededError,
    DemoCal1bError,
    DemoCal1bPrereqError,
    run_demo_cal1b_stage21,
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
from irp_shared.demo.con1_stage19 import (
    Con1Stage19Summary,
    DemoCon1AlreadySeededError,
    DemoCon1Error,
    run_demo_con1_stage19,
)
from irp_shared.demo.data1_stage22 import (
    Data1Stage22Summary,
    DemoData1AlreadySeededError,
    DemoData1Error,
    run_demo_data1_stage22,
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
from irp_shared.demo.lim2_stage20 import (
    DemoLim2AlreadySeededError,
    DemoLim2Error,
    DemoLim2PrereqError,
    Lim2Stage20Summary,
    run_demo_lim2_stage20,
)
from irp_shared.demo.lq1_stage23 import (
    DemoLq1AlreadySeededError,
    DemoLq1Error,
    Lq1Stage23Summary,
    run_demo_lq1_stage23,
)
from irp_shared.demo.multifamily import (
    DemoMultifamilyAlreadySeededError,
    DemoMultifamilyError,
    DemoMultifamilyPrereqError,
    MultifamilyExtensionSummary,
    run_demo_multifamily_extension,
)
from irp_shared.demo.ops_stage14 import (
    DemoOpsAlreadySeededError,
    DemoOpsError,
    DemoOpsPrereqError,
    OpsStage14Summary,
    run_demo_ops_stage14,
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
from irp_shared.demo.ref1_stage18 import (
    DemoRef1AlreadySeededError,
    DemoRef1Error,
    Ref1Stage18Summary,
    run_demo_ref1_stage18,
)
from irp_shared.demo.repro2_stage24 import (
    DemoRepro2AlreadySeededError,
    run_demo_repro2_stage24,
)
from irp_shared.demo.rm1_stage16 import (
    DemoRm1AlreadySeededError,
    DemoRm1Error,
    Rm1Stage16Summary,
    run_demo_rm1_stage16,
)
from irp_shared.demo.rs1_stage5 import (
    DemoRs1AlreadySeededError,
    DemoRs1Error,
    DemoRs1PrereqError,
    Rs1Stage5Summary,
    run_demo_rs1_stage5,
)
from irp_shared.demo.sch2_stage15 import (
    DemoSch2AlreadySeededError,
    DemoSch2Error,
    DemoSch2PrereqError,
    Sch2Stage15Summary,
    run_demo_sch2_stage15,
)
from irp_shared.demo.sr1_stage17 import (
    DemoSr1AlreadySeededError,
    DemoSr1Error,
    Sr1Stage17Summary,
    run_demo_sr1_stage17,
)
from irp_shared.demo.stage10_api1 import (
    DemoStage10AlreadySeededError,
    DemoStage10Error,
    DemoStage10PrereqError,
    Stage10Api1Summary,
    run_demo_stage10_api1,
)
from irp_shared.demo.struct1_stage25 import (
    DemoStruct1AlreadySeededError,
    run_demo_struct1_stage25,
)
from irp_shared.demo.struct3_stage26 import (
    DemoStruct3AlreadySeededError,
    DemoStruct3Error,
    run_demo_struct3_stage26,
)
from irp_shared.demo.struct4_stage27 import (
    DemoStruct4AlreadySeededError,
    DemoStruct4Error,
    run_demo_struct4_stage27,
)

__all__ = [
    "run_demo_rm1_stage16",
    "Rm1Stage16Summary",
    "DemoRm1Error",
    "DemoRm1AlreadySeededError",
    "run_demo_sr1_stage17",
    "run_demo_ref1_stage18",
    "Con1Stage19Summary",
    "DemoCon1AlreadySeededError",
    "DemoCon1Error",
    "run_demo_con1_stage19",
    "run_demo_lim2_stage20",
    "DemoLim2AlreadySeededError",
    "DemoLim2Error",
    "DemoLim2PrereqError",
    "Lim2Stage20Summary",
    "DemoRef1Error",
    "DemoRef1AlreadySeededError",
    "Ref1Stage18Summary",
    "Sr1Stage17Summary",
    "DemoSr1Error",
    "DemoSr1AlreadySeededError",
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
    "DemoSch2AlreadySeededError",
    "DemoSch2Error",
    "DemoSch2PrereqError",
    "Sch2Stage15Summary",
    "run_demo_sch2_stage15",
    "DemoOpsAlreadySeededError",
    "DemoOpsError",
    "DemoOpsPrereqError",
    "OpsStage14Summary",
    "run_demo_ops_stage14",
    "Cal1bStage21Summary",
    "DemoCal1bAlreadySeededError",
    "DemoCal1bError",
    "DemoCal1bPrereqError",
    "run_demo_cal1b_stage21",
    "Data1Stage22Summary",
    "DemoData1AlreadySeededError",
    "DemoData1Error",
    "run_demo_data1_stage22",
    "run_demo_lq1_stage23",
    "run_demo_repro2_stage24",
    "DemoRepro2AlreadySeededError",
    "run_demo_struct1_stage25",
    "DemoStruct1AlreadySeededError",
    "run_demo_struct3_stage26",
    "DemoStruct3AlreadySeededError",
    "DemoStruct3Error",
    "run_demo_struct4_stage27",
    "DemoStruct4AlreadySeededError",
    "DemoStruct4Error",
    "DemoLq1AlreadySeededError",
    "DemoLq1Error",
    "Lq1Stage23Summary",
]
