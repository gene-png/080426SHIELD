/**
 * #556, review round 3 A: a WITHHELD ATT&CK report is listed with its reason
 * as the summary and no files. Its status must not read "Final".
 */
import "@testing-library/jest-dom/vitest";

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { type ClientDeliverable, ResultsList } from "./ResultsList";

function row(over: Partial<ClientDeliverable>): ClientDeliverable {
  return {
    id: "d1",
    service_id: "s1",
    service_kind: "attack_coverage",
    service_title: "ATT&CK Coverage",
    title: "ATT&CK Coverage v1",
    summary: null,
    version: 1,
    released_at: "2026-09-01T00:00:00Z",
    superseded: false,
    withheld: false,
    pdf_artifact_id: null,
    xlsx_artifact_id: null,
    docx_artifact_id: null,
    pdf_filename: null,
    xlsx_filename: null,
    docx_filename: null,
    ...over,
  };
}

describe("ResultsList status (#556)", () => {
  it("marks a withheld report Withheld, not Final", () => {
    render(
      <ResultsList items={[row({ withheld: true, summary: "Withheld." })]} />,
    );
    expect(screen.getByText("Withheld")).toBeInTheDocument();
    expect(screen.queryByText("Final")).not.toBeInTheDocument();
  });

  it("marks a readable report Final", () => {
    render(<ResultsList items={[row({})]} />);
    expect(screen.getByText("Final")).toBeInTheDocument();
    expect(screen.queryByText("Withheld")).not.toBeInTheDocument();
  });
});
