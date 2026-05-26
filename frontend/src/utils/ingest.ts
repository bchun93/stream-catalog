import type { IngestJob } from "../types";

export function ingestJobSummary(job: Pick<IngestJob, "ingested_count" | "skipped_count" | "failed_count">): string {
  return `${job.ingested_count} ingested · ${job.skipped_count} skipped · ${job.failed_count} failed`;
}
