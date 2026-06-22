# Enterprise Investment Risk Platform Capability Map

> **CAP ID annotation (closes OQ-001).** The **authoritative capability taxonomy** is
> [requirements_backbone.md §4](../02_requirements/requirements_backbone.md) (CAP-1 … CAP-19). This map is the higher-level
> business view and is now annotated with the corresponding `CAP-x.y` IDs. Where this map and the backbone differ, the
> **backbone governs**. Content below is preserved; only CAP IDs and this header were added.

## Document Control

| Field | Value |
|---|---|
| Document ID | PRODSTRAT-CAPMAP-001 |
| Version | 0.2 (annotated with CAP IDs) |
| Status | Accepted (annotated) |
| Owner | H-07 Product Owner |
| Created | 2026-06-17 |
| Last Reviewed | 2026-06-18 |
| Related Documents | ../02_requirements/requirements_backbone.md, ../02_requirements/requirements_traceability_matrix.md |

## Section → CAP-domain mapping (14 map sections → 19 CAP domains)

The backbone expands these 14 sections into 19 domains via **2 splits** and **3 elevated/added domains**:

| Map § | Title | CAP domain(s) | Relationship |
|---|---|---|---|
| 1 | Portfolio and Position Management | CAP-1 | 1:1 |
| 2 | Public Asset Data | CAP-3 (+ **CAP-2**) | Security Master & Reference Data **split out** as CAP-2 |
| 3 | Private Asset Data | CAP-4 | 1:1 |
| 4 | Market Risk | CAP-5 | 1:1 |
| 5 | Credit Risk | CAP-6 | 1:1 |
| 6 | Counterparty Risk | CAP-7 | 1:1 |
| 7 | Liquidity Risk | CAP-8 | 1:1 |
| 8 | Scenario and Stress Testing | CAP-9 | 1:1 |
| 9 | Limits and Breaches | CAP-10 + CAP-11 | **split** → Limit Monitoring + Breach Workflow |
| 10 | Model Governance | CAP-12 | 1:1 |
| 11 | Data Governance | CAP-13 + CAP-14 | **split** → Data Quality & Reconciliation + Data Lineage |
| 12 | Reporting | CAP-16 | 1:1 |
| 13 | Security and Administration | CAP-17 (+ **CAP-15**) | Auditability **elevated** as CAP-15 |
| 14 | Integration Readiness | CAP-18 | 1:1 |
| — | *(not a map section)* | **CAP-2** Security Master & Reference Data | new/elevated domain. Sub-caps: 2.1 instrument · 2.2 issuer/counterparty · 2.3 identifier xref · 2.4 corporate actions · **2.5a calendars** · **2.5b currencies/rating scales** *(2.5 re-partitioned P1B-0: 2.5a→REQ-SMR-004, 2.5b→REQ-SMR-005)* |
| — | *(not a map section)* | **CAP-15** Auditability | new/elevated cross-cutting domain (audit framework exists in foundation) |
| — | *(not a map section)* | **CAP-19** BAU AI Agent Support | added domain (see `../00_ai_operating_model/bau_ai_use_cases.md`) |

## 1. Portfolio and Position Management  *(CAP-1)*
- Portfolio hierarchy (CAP-1.1)
- Fund hierarchy (CAP-1.1)
- Strategy hierarchy (CAP-1.1)
- Position master (CAP-1.2)
- Transaction history (CAP-1.3)
- Valuation history (CAP-1.4)
- Exposure aggregation (CAP-1.5)

## 2. Public Asset Data  *(CAP-3; instrument/reference content → CAP-2 Security Master & Reference Data)*
- Listed equities (CAP-2.1 instrument master)
- Public fixed income (CAP-2.1)
- Derivatives (CAP-2.1)
- FX (CAP-2.1)
- Cash (CAP-2.1)
- Market prices (CAP-3.1)
- Yield curves (CAP-3.2)
- Volatility data (CAP-3.3)
- Credit spreads (CAP-3.4)
- Ratings (CAP-3.5; rating scales → CAP-2.5b)
- Benchmarks (CAP-3.5)

## 3. Private Asset Data  *(CAP-4)*
- Private equity funds (CAP-4.1)
- Private credit funds (CAP-4.1)
- Direct private loans (CAP-4.1)
- Real estate (CAP-4.1)
- Infrastructure (CAP-4.1)
- Commitments (CAP-4.1)
- Funded and unfunded exposure (CAP-4.1)
- Capital calls (CAP-4.2)
- Distributions (CAP-4.2)
- GP NAV reports (CAP-4.3)
- Appraisals (CAP-4.3)
- Private company financials (CAP-4.4; DC-4 / MNPI)
- Valuation dates (CAP-4.5)
- Stale valuation flags (CAP-4.5)
- Proxy mappings (CAP-4.5)

## 4. Market Risk  *(CAP-5)*
- Value at Risk (CAP-5.1)
- Expected Shortfall (CAP-5.1)
- Sensitivities (CAP-5.2)
- Duration (CAP-5.2)
- Convexity (CAP-5.2)
- Spread duration (CAP-5.2)
- Factor exposure (CAP-5.3)
- Factor contribution (CAP-5.3)
- Drawdown (CAP-5.4)
- Basis risk (CAP-5.4)
- Stress testing (CAP-5.5)

## 5. Credit Risk  *(CAP-6)*
- Probability of Default (CAP-6.1)
- Loss Given Default (CAP-6.1)
- Exposure at Default (CAP-6.1)
- Expected Loss (CAP-6.1)
- Credit migration (CAP-6.2)
- Spread risk (CAP-6.3)
- Concentration (CAP-6.4)
- Default stress (CAP-6.2)
- Downgrade stress (CAP-6.2)
- Shadow ratings (CAP-6.5)
- Internal ratings (CAP-6.5)

## 6. Counterparty Risk  *(CAP-7)*
- Current exposure (CAP-7.1)
- Potential future exposure (CAP-7.2)
- Expected positive exposure (CAP-7.2)
- Netting sets (CAP-7.3)
- Collateral (CAP-7.3)
- CSA terms (CAP-7.3)
- Counterparty limits (CAP-7.4)
- Wrong-way risk (CAP-7.4)
- CVA placeholder (CAP-7.5)

## 7. Liquidity Risk  *(CAP-8)*
- Liquidity classification (CAP-8.1)
- Illiquid asset percentage (CAP-8.1)
- Highly liquid asset coverage (CAP-8.1)
- Redemption stress (CAP-8.2)
- Liquidity waterfall (CAP-8.2)
- Transaction cost (CAP-8.2)
- Funding liquidity (CAP-8.3)
- Credit facility usage (CAP-8.3)
- Margin call stress (CAP-8.4)
- Capital call forecasting (CAP-8.5)
- Contingency funding plan indicators (CAP-8.5)

## 8. Scenario and Stress Testing  *(CAP-9)*
- Historical scenarios (CAP-9.1)
- Hypothetical scenarios (CAP-9.2)
- Reverse stress testing (CAP-9.3)
- Macro scenarios (CAP-9.2)
- Liquidity stress (CAP-9.4)
- Credit stress (CAP-9.4)
- Private asset valuation shock (CAP-9.5)
- Combined market-credit-liquidity stress (CAP-9.4)

## 9. Limits and Breaches  *(CAP-10 Limit Monitoring + CAP-11 Breach Workflow — split)*
- Limit framework (CAP-10.1)
- Limit utilization (CAP-10.2)
- Soft limits (CAP-10.3)
- Hard limits (CAP-10.3)
- Breach detection (CAP-10.4)
- Breach workflow (CAP-11.1)
- Remediation plan (CAP-11.2)
- 1st Line response (CAP-11.2)
- 2nd Line review (CAP-11.3)
- Escalation (CAP-11.4)
- Closure evidence (CAP-11.4)

## 10. Model Governance  *(CAP-12)*
- Model inventory (CAP-12.1)
- Model versioning (CAP-12.2)
- Model assumptions (CAP-12.2)
- Model limitations (CAP-12.2)
- Model validation workflow (CAP-12.4)
- Model tiering (CAP-12.3)
- Effective challenge evidence (CAP-12.4)
- Approval status (CAP-12.5)
- Restricted use status (CAP-12.5)

## 11. Data Governance  *(CAP-13 Data Quality & Reconciliation + CAP-14 Data Lineage — split)*
- Data dictionary (CAP-13; defined in `../04_data_model/canonical_data_model_standard.md`)
- Data quality rules (CAP-13.1)
- Reconciliation (CAP-13.2)
- Manual overrides (CAP-13.4)
- Data lineage (CAP-14.1 / CAP-14.2)
- Source-to-target mapping (CAP-14.1)
- Data quality dashboard (CAP-13.3)
- Exception management (CAP-13.3)

## 12. Reporting  *(CAP-16)*
- Portfolio risk report (CAP-16.1)
- Market risk report (CAP-16.1)
- Credit risk report (CAP-16.1)
- Liquidity risk report (CAP-16.1)
- Scenario report (CAP-16.2)
- Breach report (CAP-16.2)
- Model inventory report (CAP-16.4)
- Data quality report (CAP-16.4)
- Board risk report (CAP-16.3)
- Audit extract (CAP-16.5 / CAP-15.3 Auditability)

## 13. Security and Administration  *(CAP-17 Administration & Entitlements; audit/logging → CAP-15 Auditability)*
- Authentication (CAP-17.1)
- Role-based access control (CAP-17.2)
- Portfolio-level entitlements (CAP-17.2)
- Admin console (CAP-17.4)
- Secrets management (CAP-17; BR-10)
- Security event logging (CAP-15.1 Auditability)
- Data export controls (CAP-17.5)
- *(SoD / maker-checker → CAP-17.3, elevated in the backbone)*

## 14. Integration Readiness  *(CAP-18)*
- CSV upload (CAP-18.1)
- Excel upload (CAP-18.1)
- API adapter (CAP-18.2)
- SFTP adapter (CAP-18.3)
- Vendor feed abstraction (CAP-18.4)
- Portfolio accounting adapter (CAP-18.4)
- Market data adapter (CAP-18.4)
- GP report ingestion adapter (CAP-18.5)
