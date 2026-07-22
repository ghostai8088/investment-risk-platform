import { useEffect, useState } from "react";

import { ApiError, apiGet } from "./client";
import type { Session } from "../session";

export interface AsyncState<T> {
  data: T | null;
  error: ApiError | null;
  loading: boolean;
}

/**
 * GET `path` (read-only) whenever it or the session changes, with a staleness guard so a superseded
 * response never renders (the RunDetail review-fold pattern, shared). Pass `path === null` to
 * intentionally HOLD — no request is made and the state is idle — e.g. until a dependency such as
 * the resolved portfolio id is available.
 */
export function useApiGet<T>(path: string | null, session: Session | null): AsyncState<T> {
  const [state, setState] = useState<AsyncState<T>>(() => ({
    data: null,
    error: null,
    loading: path !== null,
  }));

  useEffect(() => {
    if (path === null) {
      setState({ data: null, error: null, loading: false });
      return;
    }
    let stale = false;
    setState({ data: null, error: null, loading: true });
    apiGet<T>(path, session)
      .then((body) => {
        if (!stale) setState({ data: body, error: null, loading: false });
      })
      .catch((e: unknown) => {
        if (!stale) {
          setState({
            data: null,
            error: e instanceof ApiError ? e : new ApiError("network", String(e)),
            loading: false,
          });
        }
      });
    return () => {
      stale = true;
    };
  }, [path, session]);

  return state;
}
