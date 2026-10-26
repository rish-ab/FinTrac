import { useCallback, useEffect, useState } from 'react';
import { ApiError } from '../api/client';

export interface QueryState<T> {
  data: T | null;
  loading: boolean;
  error: Error | null;
  updatedAt: Date | null;
  refresh: () => void;
}

export function useApiQuery<T>(loader: () => Promise<T>, deps: unknown[] = []): QueryState<T> {
  const [revision, setRevision] = useState(0);
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);
  const [updatedAt, setUpdatedAt] = useState<Date | null>(null);
  const refresh = useCallback(() => setRevision((value) => value + 1), []);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    loader().then((result) => {
      if (!active) return;
      setData(result);
      setUpdatedAt(new Date());
    }).catch((reason: unknown) => {
      if (!active) return;
      setError(reason instanceof Error ? reason : new Error('Request failed'));
    }).finally(() => {
      if (active) setLoading(false);
    });
    return () => { active = false; };
    // Loader identity is intentionally controlled by deps and revision.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, revision]);

  return { data, loading, error, updatedAt, refresh };
}

export function errorTitle(error: Error | null): string {
  if (!error) return 'Unable to load data';
  if (!(error instanceof ApiError)) return error.message || 'Unable to load data';
  if (error.status === 0) return 'Connection issue';
  if (error.status === 401) return 'Sign in required';
  if (error.status === 403) return 'Access denied';
  if (error.status === 429) return 'Rate limit reached';
  if (error.status >= 500) return 'API service unavailable';
  return error.message || `Request failed (${error.status})`;
}
