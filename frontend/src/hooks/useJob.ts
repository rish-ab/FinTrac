import { useCallback, useEffect, useRef, useState } from 'react';
import { ApiError, api } from '../api/client';
import type { Job } from '../api/types';

const FINISHED = new Set(['completed', 'failed', 'cancelled']);
const POLL_MS = 2_000;

function readStored(key: string): string | null {
  try { return window.sessionStorage.getItem(key); } catch { return null; }
}
function writeStored(key: string, value: string | null): void {
  try {
    if (value) window.sessionStorage.setItem(key, value);
    else window.sessionStorage.removeItem(key);
  } catch { /* storage unavailable: polling still works for this page view */ }
}

export interface JobState<T extends Job> {
  job: T | null;
  /** Set when polling itself fails (e.g. the API restarted and the job is gone). */
  error: Error | null;
  running: boolean;
  track: (job: T) => void;
  cancel: () => Promise<void>;
  clear: () => void;
}

/**
 * Polls GET /jobs/{id} until the job finishes.
 * The id is kept in sessionStorage under `storageKey`, so navigating away
 * or refreshing re-attaches to a job that is still running on the API.
 */
export function useJob<T extends Job>(storageKey: string): JobState<T> {
  const [jobId, setJobId] = useState<string | null>(() => readStored(storageKey));
  const [job, setJob] = useState<T | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [lost, setLost] = useState(false);
  const timer = useRef<number | null>(null);

  const stop = useCallback(() => {
    if (timer.current !== null) window.clearTimeout(timer.current);
    timer.current = null;
  }, []);

  useEffect(() => {
    if (!jobId) return;
    let active = true;

    const poll = async () => {
      try {
        const next = await api.job<T>(jobId);
        if (!active) return;
        setJob(next);
        setError(null);
        if (FINISHED.has(next.status)) {
          writeStored(storageKey, null);
          return;
        }
      } catch (reason) {
        if (!active) return;
        if (reason instanceof ApiError && reason.status === 404) {
          // Jobs live in API memory; a restart (or uvicorn --reload) drops them
          setError(new Error('The job is no longer known to the API. It may have expired, or the API restarted while it was running.'));
          setLost(true);
          writeStored(storageKey, null);
          return;
        }
        // Transient network error: keep the last known state and retry
        setError(reason instanceof Error ? reason : new Error('Lost contact with the API'));
      }
      timer.current = window.setTimeout(poll, POLL_MS);
    };

    void poll();
    return () => { active = false; stop(); };
  }, [jobId, storageKey, stop]);

  const track = useCallback((started: T) => {
    stop();
    writeStored(storageKey, started.id);
    setError(null);
    setLost(false);
    setJob(started);
    setJobId(started.id);
  }, [storageKey, stop]);

  const cancel = useCallback(async () => {
    if (!jobId) return;
    await api.cancelJob(jobId);
    // The next poll picks up the 'cancelled' status
  }, [jobId]);

  const clear = useCallback(() => {
    stop();
    writeStored(storageKey, null);
    setJobId(null);
    setJob(null);
    setError(null);
    setLost(false);
  }, [storageKey, stop]);

  const running = Boolean(job && !FINISHED.has(job.status) && !lost);
  return { job, error, running, track, cancel, clear };
}
