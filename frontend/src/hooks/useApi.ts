import { useCallback, useEffect, useRef, useState } from 'react';

interface ApiState<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
}

/**
 * Minimal data-fetching hook.
 *
 * Deliberately small: loading/error state plus a `reload` callback is all this UI needs.
 * Requests are guarded against setting state after unmount and against out-of-order responses.
 */
export function useApi<T>(fetcher: () => Promise<T>, deps: unknown[] = []): ApiState<T> & {
  reload: () => void;
} {
  const [state, setState] = useState<ApiState<T>>({ data: null, loading: true, error: null });
  const requestId = useRef(0);
  const mounted = useRef(true);

  const run = useCallback(() => {
    const current = ++requestId.current;
    setState((previous) => ({ ...previous, loading: true, error: null }));

    fetcher()
      .then((data) => {
        if (!mounted.current || current !== requestId.current) return;
        setState({ data, loading: false, error: null });
      })
      .catch((error: unknown) => {
        if (!mounted.current || current !== requestId.current) return;
        setState({
          data: null,
          loading: false,
          error: error instanceof Error ? error.message : 'Request failed',
        });
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  useEffect(() => {
    mounted.current = true;
    run();
    return () => {
      mounted.current = false;
    };
  }, [run]);

  return { ...state, reload: run };
}
