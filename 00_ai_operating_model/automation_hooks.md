# Automation Hooks

## Purpose

Define deterministic automations that should run during AI-assisted development and eventually during platform operations.

Hooks are used for rules that should always execute, rather than relying on an AI agent to remember them.

## Development Hooks

## 1. Post-Edit Formatting Hook

Trigger:
- After AI edits source code.

Action:
- Run formatter.
- Run linter where appropriate.

Purpose:
- Maintain code consistency.

## 2. Pre-Commit Test Hook

Trigger:
- Before code is committed.

Action:
- Run unit tests.
- Run calculation benchmark tests.
- Run type checks.
- Run lint checks.

Purpose:
- Prevent broken code from entering the repository.

## 3. Security Scan Hook

Trigger:
- Before pull request or release.

Action:
- Run dependency scan.
- Run static security scan.
- Check for secrets.

Purpose:
- Identify security issues early.

## 4. Documentation Consistency Hook

Trigger:
- When analytics, data model, API, or workflows change.

Action:
- Check whether related documentation was updated.

Purpose:
- Prevent code and documentation drift.

## 5. Model Inventory Hook

Trigger:
- When a calculation module is added or changed.

Action:
- Check whether model inventory and methodology documentation were updated.

Purpose:
- Maintain model governance discipline.

## Platform BAU Hooks

## 1. Data Load Completion Hook

Trigger:
- After data ingestion completes.

Action:
- Run data quality rules.
- Create data quality summary.
- Create audit event.

## 2. Calculation Run Hook

Trigger:
- After risk calculation completes.

Action:
- Save calculation run metadata.
- Save model version.
- Save assumption set.
- Save lineage.
- Create audit event.

## 3. Breach Detection Hook

Trigger:
- When a limit breach is detected.

Action:
- Create breach record.
- Notify assigned owner.
- Generate breach triage summary.
- Start workflow timer.

## 4. Report Generation Hook

Trigger:
- When a report is generated.

Action:
- Save report version.
- Save source metric versions.
- Save calculation run IDs.
- Create audit event.

## 5. Model Monitoring Hook

Trigger:
- On scheduled model monitoring cycle.

Action:
- Run monitoring tests.
- Flag exceptions.
- Update validation dashboard.