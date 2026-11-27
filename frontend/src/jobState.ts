import type { Job, JobLane, ProgressEvent } from "./api";

const LANE_NAME: Record<JobLane, string> = { block1: "Khối 1", block2: "Khối 2" };

/** Job to track after a job-starting POST returns — null if its terminal event already arrived (fast job). */
export function jobAfterStart(jobId: string, finished: Set<string>, lane: JobLane = "block1",
  setId: number | null = null, exclusive = false): Job | null {
  return finished.has(jobId) ? null
    : { id: jobId, name: LANE_NAME[lane], done: 0, total: 0, lane, set_id: setId, exclusive };
}

/** Add `job` (or replace the one with its id); null leaves the list as it is. */
export function upsertJob(jobs: Job[], job: Job | null): Job[] {
  if (!job) return jobs;
  return jobs.some((j) => j.id === job.id) ? jobs.map((j) => (j.id === job.id ? job : j)) : [...jobs, job];
}

export function removeJob(jobs: Job[], id: string): Job[] {
  return jobs.filter((j) => j.id !== id);
}

/** Progress of a running job from a ws event; a job we did not know about yet is added. */
export function progressJob(jobs: Job[], e: ProgressEvent): Job[] {
  const known = jobs.find((j) => j.id === e.job_id);
  if (known) return upsertJob(jobs, { ...known, done: e.done, total: e.total });
  const lane = e.lane ?? "block1";
  return [...jobs, { id: e.job_id, name: LANE_NAME[lane], done: e.done, total: e.total, lane, set_id: null }];
}

/** Reconcile with /api/jobs or /api/health: the server decides which jobs run; local progress may be ahead. */
export function jobsFromServer(local: Job[], server: Job[]): Job[] {
  return server.map((s) => {
    const l = local.find((j) => j.id === s.id);
    return l && l.done >= s.done ? { ...s, done: l.done, total: l.total } : s;
  });
}

/** Same rule as the server: one job per lane; on one audio set only an `exclusive` job (ours or theirs) clashes. */
export function laneBlocker(jobs: Job[], lane: JobLane, setId: number | null, exclusive = false): Job | null {
  return jobs.find((j) => j.lane === lane
    || (setId !== null && j.set_id === setId && (exclusive || !!j.exclusive))) ?? null;
}

/** Why the lane's buttons are off, for their tooltip. */
export function blockReason(blocker: Job | null, lane: JobLane): string | null {
  if (!blocker) return null;
  return blocker.lane === lane
    ? `Đang chạy: ${blocker.name}`
    : `Đang chạy: ${blocker.name} trên cùng bộ audio — đợi xong hoặc dừng job đó`;
}
