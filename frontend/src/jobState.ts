import type { Job } from "./api";

/** Job to track after POST /block1 returns — null if its terminal event already arrived (fast job). */
export function jobAfterStart(jobId: string, finished: Set<string>): Job | null {
  return finished.has(jobId) ? null : { id: jobId, name: "Khối 1", done: 0, total: 0 };
}

/** Reconcile with /api/health or /api/jobs/current: the server decides whether a job runs. */
export function jobFromServer(local: Job | null, server: Job | null): Job | null {
  if (!server) return null;
  if (local && local.id === server.id && local.done >= server.done) return local;
  return server;
}
