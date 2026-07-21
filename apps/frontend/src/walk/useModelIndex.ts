import { useEffect, useState } from "react";

import { ApiError, apiGet } from "../api/client";
import type { DevSession } from "../session";

/** Minimal shapes of the governance reads this index consumes (orchestration over the stable
 * /models + /models/{id} surface; the row DTOs bound elsewhere carry the FE-2 drift guard). */
interface ModelSummary {
  id: string;
}
interface Validation {
  outcome: string;
  validation_type: string;
  overdue: boolean;
}
interface ModelVersion {
  id: string;
  limitations: string[];
  latest_validation: Validation | null;
}
interface ModelDetail {
  id: string;
  code: string;
  tier: string | null;
  versions: ModelVersion[];
}

/** The governance context for one model_version — powers the inline validation badge + disclosed
 * limitations on every governed number (OD-FE-3-C). */
export interface ModelEntry {
  modelCode: string;
  tier: string | null;
  outcome: string | null;
  overdue: boolean | null;
  validationType: string | null;
  limitations: string[];
}

export interface ModelIndex {
  /** model_version_id → its governance context (empty while loading / if not entitled). */
  entries: Map<string, ModelEntry>;
  loading: boolean;
  /** Set if `/models` is not readable (e.g. a viewer without `model.inventory.view`) — the numbers
   * still render their value + provenance; only the validation/limitations sub-panes degrade. */
  error: ApiError | null;
}

/**
 * Build a model_version_id → governance map by reading `/models` then each `/models/{id}` (the demo
 * inventory is small; the detail reads run in parallel). Gated `model.inventory.view` — a 403 here
 * degrades the validation/limitations sub-panes only, never the governed numbers themselves.
 */
export function useModelIndex(session: DevSession): ModelIndex {
  const [state, setState] = useState<ModelIndex>({
    entries: new Map(),
    loading: true,
    error: null,
  });

  useEffect(() => {
    let stale = false;
    setState({ entries: new Map(), loading: true, error: null });
    void (async () => {
      try {
        const models = await apiGet<ModelSummary[]>("/models", session);
        const details = await Promise.all(
          models.map((m) => apiGet<ModelDetail>(`/models/${encodeURIComponent(m.id)}`, session)),
        );
        if (stale) return;
        const entries = new Map<string, ModelEntry>();
        for (const d of details) {
          for (const v of d.versions) {
            entries.set(v.id, {
              modelCode: d.code,
              tier: d.tier,
              outcome: v.latest_validation?.outcome ?? null,
              overdue: v.latest_validation?.overdue ?? null,
              validationType: v.latest_validation?.validation_type ?? null,
              limitations: v.limitations,
            });
          }
        }
        setState({ entries, loading: false, error: null });
      } catch (e) {
        if (!stale) {
          setState({
            entries: new Map(),
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
