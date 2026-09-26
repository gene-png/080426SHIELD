import { describe, expect, it } from "vitest";

import type { CapabilityItem, CapabilityList } from "./types";

import { draftSourceArtifactId } from "./draftSource";

// #644. Mirrors the API's `_draft_source_artifact_id`: the one document an
// open draft's rows came from, or null when that cannot be established.
function list(
  status: CapabilityList["status"],
  sources: (string | null)[],
): CapabilityList {
  return {
    status,
    items: sources.map(
      (s, i) => ({ id: `i${i}`, source_artifact_id: s }) as CapabilityItem,
    ),
  } as unknown as CapabilityList;
}

describe("draftSourceArtifactId (#644)", () => {
  it("names the single document an open draft came from", () => {
    expect(draftSourceArtifactId(list("draft", ["doc-a", "doc-a", null]))).toBe(
      "doc-a",
    );
  });

  it("is null for a list that is not an open draft", () => {
    expect(draftSourceArtifactId(list("approved", ["doc-a"]))).toBeNull();
    expect(draftSourceArtifactId(null)).toBeNull();
  });

  it("is null when no row names a document, or rows name two", () => {
    expect(draftSourceArtifactId(list("draft", [null, null]))).toBeNull();
    expect(draftSourceArtifactId(list("draft", ["doc-a", "doc-b"]))).toBeNull();
  });
});
