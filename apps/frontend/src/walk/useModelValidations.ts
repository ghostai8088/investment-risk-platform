import { useEffect, useState } from "react";

import { ApiError, apiGet } from "../api/client";
import type { ValidationDetail, ValidationSummary } from "../api/types";
import type { Session } from "../session";

interface ModelSummary {
  id: string;
}
interface ModelVersion {
  id: string;
  version_label: string;
  latest_validation: { outcome: string } | null;
}
interface ModelDetail {
  id: string;
  code: string;
  tier: string | null;
  versions: ModelVersion[];
}

export interface ValidationCard {
  modelCode: string;
  tier: string | null;
  versionLabel: string;
  detail: ValidationDetail;
}

export interface ModelValidations {
  cards: ValidationCard[];
  loading: boolean;
  error: ApiError | null;
}

/**
 * Assemble the demo's validation records WITH their findings + evidence (the F2 governance reads
 * that were write-only before API-1): `/models` → each `/models/{id}` → the LATEST validated version
 * → its `/validations` (summary, for the id) → the validation `detail` (findings + evidence).
 * Gated `model.inventory.view`; a 403 degrades the whole step to a calm note.
 */
export function useModelValidations(session: Session): ModelValidations {
  const [state, setState] = useState<ModelValidations>({ cards: [], loading: true, error: null });

  useEffect(() => {
    let stale = false;
    setState({ cards: [], loading: true, error: null });
    void (async () => {
      try {
        const models = await apiGet<ModelSummary[]>("/models", session);
        const details = await Promise.all(
          models.map((m) => apiGet<ModelDetail>(`/models/${encodeURIComponent(m.id)}`, session)),
        );
        const targets = details.flatMap((d) => {
          // `/models/{id}` orders versions ASCENDING by version_label, so the LAST validated one is
          // the most-recent version's validation — show that, not the oldest (a re-versioned,
          // re-validated model is exactly the governance lifecycle this step narrates).
          const validated = d.versions.filter((ver) => ver.latest_validation !== null);
          const v = validated.length > 0 ? validated[validated.length - 1] : undefined;
          return v ? [{ d, v }] : [];
        });
        const cards = await Promise.all(
          targets.map(async ({ d, v }): Promise<ValidationCard | null> => {
            const list = await apiGet<ValidationSummary[]>(
              `/models/${encodeURIComponent(d.id)}/versions/${encodeURIComponent(v.id)}/validations`,
              session,
            );
            if (list.length === 0) return null;
            const detail = await apiGet<ValidationDetail>(
              `/models/${encodeURIComponent(d.id)}/validations/${encodeURIComponent(list[0].id)}`,
              session,
            );
            return { modelCode: d.code, tier: d.tier, versionLabel: v.version_label, detail };
          }),
        );
        if (!stale) {
          setState({
            cards: cards.filter((c): c is ValidationCard => c !== null),
            loading: false,
            error: null,
          });
        }
      } catch (e) {
        if (!stale) {
          setState({
            cards: [],
            loading: false,
            error: e instanceof ApiError ? e : new ApiError("network", String(e)),
          });
        }
      }
    })();
    return () => {
      stale = true;
    };
  }, [session]);

  return state;
}
