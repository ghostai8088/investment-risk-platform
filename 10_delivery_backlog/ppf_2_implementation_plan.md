# PPF-2 Implementation Plan — the private covariance block Ω_pp (Wave-10 slice 3, §2.1 arc slice 2)

Companion to `ppf_2_decision_record.md` (read it first — the ODs/ratified OQs/verifier folds govern). One commit per step; `make check` green at each boundary. **NO migration** (OQ-4=A). Model counts move 18→19 governed numbers at the demo step.

## Step sequence

1. **The isolation fold FIRST (verifier CLAIM 2) — the three run_type read-filters.**
   Add `run_type=RUN_TYPE_COVARIANCE` to `latest_covariances` (`risk/covariance_service.py:415-433`, the `list_governed_results` call) + a run_type predicate to `resolve_covariance` (by-id) + the `GET /covariances/latest` / `GET /covariances/{id}` endpoints. Add `COVARIANCE_PRIVATE` to `RISK_RUN_TYPES` (`risk/queries.py`). **Regression proof: behavior-identical for all existing data** — a test asserting the public covariance reads return the SAME rows before/after (no private rows exist yet), plus the reads.py shared-table-contract now honored. This lands before any private rows can exist, closing the latent bug.

2. **Vocab + registrar mints.**
   `RUN_TYPE_COVARIANCE_PRIVATE` + `RISK_COVARIANCE_PRIVATE_CREATE_EVENT_RESERVED` (`risk/events.py`); `PurePrivateCovarianceActor`. `PURPOSE_PRIVATE_COVARIANCE_INPUT` + `COMPONENT_KIND_PURE_PRIVATE_RETURN` (`snapshot/models.py`, added to the allow-list + the SNAPSHOT_PURPOSES tuple). The registrar `register_private_covariance_model` (`risk/bootstrap.py`, mirroring `register_covariance_model`): model code `risk.covariance.private`, declared `window_observations` identity (reuse `declared_window_observations` — the window is the number of common appraisal periods, floor N≥2), methodology ref, assumptions (equal-weight sample covariance over the pure-private APPRAISAL series; block-diagonal-approx disclosure; thin-N + shrinkage-is-v2; the pure-private-orthogonality-is-approximate limitation) + limitations.

3. **The serializer + snapshot builder.**
   `pure_private_return_content` (`snapshot/serialize.py`, mirroring `desmoothed_return_content` — pins `segment_factor_id`/`metric_type`/`period_start`/`period_end`/`metric_value`, the governed-row no-valid-axis flavor). `build_private_covariance_snapshot` (`snapshot/service.py`, mirroring `build_covariance_snapshot`): resolve the ≥2 segment factors (assert PRIVATE family), list each's `PURE_PRIVATE_PERIOD` rows via a `_list_pure_private_period_rows` helper, **intersect to the common `(period_start, period_end)` grid** (the "N most-recent common intervals" precedent), fail-closed below N≥2, pin each segment's `COMPONENT_KIND_FACTOR` (the segment factor def) + `COMPONENT_KIND_PURE_PRIVATE_RETURN` (the aligned series). `PURPOSE_PRIVATE_COVARIANCE_INPUT`, a binding predicate ≤50 chars.

4. **The binder (`risk/private_covariance_service.py`).**
   `run_private_covariance` via `execute_governed_run`: pre-create gate; resolve+identity-check the `risk.covariance.private` model version; build-in-request (`segment_factor_ids`) or consume-existing (`snapshot_id`, purpose-checked); an **APPRAISAL-aware adjudicator** (the `covariance_service.py:184-193` DAILY/SIMPLE checks → APPRAISAL/SIMPLE over the PURE_PRIVATE_RETURN pin shape; re-key each row on `period_end`; assert the identical date vector); feed the **reused `estimate_covariance` kernel**; persist `CovarianceResult` rows (frequency=`APPRAISAL`, statistic_type=`COVARIANCE`, the segment factor pair keys) via the scaffold. The magnitude gate (reuse the covariance envelope). Rule-7 reads: `list_private_covariances` (by run) + `latest_private_covariances` (by the segment set, `run_type=COVARIANCE_PRIVATE`-filtered) + `resolve_private_covariance`.

5. **API reads + OpenAPI regen.**
   `GET /risk/private-covariances[/latest,/{id}]` (`risk.view`-gated), reusing `CovarianceRowOut` (frequency renders `APPRAISAL`). Regenerate `openapi.json` + FE types; the exhaustive decimal guard already covers `CovarianceRowOut` (no new DTO) — confirm `make gen-api-check` clean.

6. **Demo stage 12 + docs.**
   Extend the demo: run ONE `risk.covariance.private` over the two seeded segments (PE-HARBOR-IV + PC-BRIDGEWATER-II) — **N=5 common quarters, ZERO new seeding** (verifier-confirmed); disclose the thin window in the summary. File ONE INITIAL AWC (a new code → SOME record). Counts move **21/36/103 → 22/37/104** (1 code + 1 record + 1 run). Filename `stage9zzz` (sorts after `stage9zz`). Docs: the 19th-governed-number counts sweep; `risk.covariance.private` in the model census; the block-diagonal-approx + thin-N limitations recorded.

7. **Gate + review.**
   `make check` + full-PG affected-family battery (incl. the public-covariance byte-identical regression) + `make fe-check` + `make gen-api-check` + `alembic check` (must stay clean — NO migration) + pip-audit. Then the 4-finder adversarial review: (1) covariance correctness vs the cited construction + the approx-orthogonality honesty; (2) doctrine/security + **public-covariance isolation** (attack: make a private run leak into a public read); (3) read-correctness + the run_type filters; (4) demo/count integrity + the thin-N disclosure. Fold; closeout per the closure-discipline check.

## Effort/model note
Step 1 (the read-filter fold) is small but load-bearing (it touches shipped public reads — regression-prove byte-identity). Steps 2-5 are the well-worn governed-number template with heavy reuse (the kernel + result table + covariance registrar are all shipped). Step 6's demo is a single run over already-seeded data.
