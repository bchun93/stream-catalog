import { describe, expect, it } from "vitest";

import { ingestJobSummary } from "./ingest";

describe("ingestJobSummary", () => {
  it("formats ingest, skipped, and failed counts", () => {
    expect(
      ingestJobSummary({
        ingested_count: 12,
        skipped_count: 3,
        failed_count: 1,
      })
    ).toBe("12 ingested · 3 skipped · 1 failed");
  });
});
