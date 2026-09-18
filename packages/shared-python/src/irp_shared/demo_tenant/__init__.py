"""BOOK-1a — the Northlight demo tenant (Wave 20 slice 1; `w20_book1a_remit.md`)."""

from irp_shared.demo_tenant import book
from irp_shared.demo_tenant.book import TENANT_CODE, TENANT_ID, TENANT_NAME
from irp_shared.demo_tenant.seed import (
    DemoTenantAlreadySeededError,
    DemoTenantError,
    SeedSummary,
    seed_demo_tenant,
)

__all__ = [
    "TENANT_CODE",
    "TENANT_ID",
    "TENANT_NAME",
    "book",
    "DemoTenantAlreadySeededError",
    "DemoTenantError",
    "SeedSummary",
    "seed_demo_tenant",
]
