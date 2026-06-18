# BAU AI Use Cases

## Objective

Capture opportunities to use AI agents during normal platform operations, not just during development.

## 1. Data Operations

### Data Quality Monitoring Agent
Purpose:
- Review daily data quality exceptions.
- Summarize missing, stale, duplicated, or anomalous data.
- Recommend remediation actions.
- Draft data steward notes.

Inputs:
- Data quality results
- Reconciliation outputs
- Prior day exceptions
- Source system status

Outputs:
- Exception summary
- Severity classification
- Suggested remediation
- Aging report
- Escalation recommendation

### Private Asset Data Review Agent
Purpose:
- Review GP reports, appraisals, valuation dates, capital calls, and distributions.
- Flag stale valuations, unusual NAV movements, missing funded/unfunded data, and inconsistent private asset identifiers.

Outputs:
- Private asset data quality summary
- NAV movement commentary
- Missing data list
- Required follow-ups

## 2. Risk Operations

### Limit Breach Triage Agent
Purpose:
- Summarize limit breaches.
- Identify likely drivers.
- Draft first-line response.
- Prepare second-line review package.

Outputs:
- Breach narrative
- Root cause hypothesis
- Impacted portfolios
- Suggested remediation
- Required approvals

### Scenario Commentary Agent
Purpose:
- Generate plain-English explanations of scenario results.
- Compare current scenario outcomes to prior runs.
- Identify key risk drivers.

Outputs:
- Scenario narrative
- Top contributors
- Portfolio impacts
- Assumption summary
- Limitations

## 3. Model Governance

### Model Performance Monitoring Agent
Purpose:
- Review model monitoring outputs.
- Flag drift, back-testing exceptions, benchmark deviations, and overdue validations.

Outputs:
- Model monitoring summary
- Validation alerts
- Limitation updates
- Recommended model review actions

### Model Documentation Agent
Purpose:
- Maintain methodology documents, assumptions, limitations, and validation evidence.

Outputs:
- Updated model documentation
- Change summaries
- Validation support package

## 4. Reporting

### Board Reporting Assistant
Purpose:
- Draft board-level risk commentary from approved metrics.
- Summarize market, credit, liquidity, private asset, scenario, and breach themes.

Outputs:
- Draft board report narrative
- Key risk highlights
- Breach summary
- Scenario summary
- Data quality caveats

### Regulatory / Due Diligence Evidence Agent
Purpose:
- Maintain evidence packs for client due diligence, internal audit, compliance review, and vendor risk assessment.

Outputs:
- Control evidence updates
- Audit extracts
- Due diligence responses
- Traceability summaries

## 5. Technology Operations

### Release Readiness Agent
Purpose:
- Review test results, open defects, security scans, migration scripts, documentation, and release notes before deployment.

Outputs:
- Release readiness checklist
- Go/no-go recommendation
- Open risk summary
- Rollback considerations

### Security Review Support Agent
Purpose:
- Review security logs, dependency scan results, permission changes, and sensitive configuration risks.

Outputs:
- Security issue summary
- Severity classification
- Suggested remediation
- Escalation recommendation