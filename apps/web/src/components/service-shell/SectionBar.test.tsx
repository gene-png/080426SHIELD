import "@testing-library/jest-dom/vitest";

import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SectionBar, type SectionKey } from "./SectionBar";

// Gene's v2 plan (#736, issuecomment-6115981718 and the full text,
// issuecomment-6116093149), verbatim and in order. Recommendations is the link
// text alone; its admin-only marker is a separate badge (coordinator ruling
// relayed from #736 issuecomment-6116092992). Written out here, not read from
// SectionBar.tsx: this is the spec.
const ADMIN_BADGE = "KENTRO ADMIN ONLY";
const GENE_LABELS = [
  "Overview",
  "Inputs",
  "AI draft",
  "Review",
  "Analysis",
  "Generate",
  "Quality check",
  "Approve and release",
  "Recommendations",
];

const hrefFor = (key: SectionKey): string => `/svc/x/${key}`;

function links(): HTMLAnchorElement[] {
  return within(screen.getByRole("navigation")).getAllByRole(
    "link",
  ) as HTMLAnchorElement[];
}

function labels(): string[] {
  return links().map((a) => a.textContent ?? "");
}

describe("SectionBar (for #1087)", () => {
  it("lists Gene's nine sections verbatim, in order", () => {
    render(<SectionBar current="overview" hrefFor={hrefFor} />);
    expect(labels()).toEqual(GENE_LABELS);
  });

  it("marks Recommendations, and only it, with a separate admin-only badge", () => {
    render(<SectionBar current="overview" hrefFor={hrefFor} />);
    const badges = screen.getAllByText(ADMIN_BADGE);
    expect(badges).toHaveLength(1);
    expect(badges[0]).toHaveAttribute("data-admin-badge");
    // The ruling: the link text is "Recommendations"; the badge sits beside
    // the link, not inside it, so it is not part of the link's name.
    const recs = screen.getByRole("link", { name: "Recommendations" });
    expect(recs).not.toContainElement(badges[0]);
    expect(recs.closest("li")).toContainElement(badges[0]);
  });

  it("makes every section a real link to its own URL", () => {
    render(<SectionBar current="overview" hrefFor={hrefFor} />);
    const hrefs = links().map((a) => a.getAttribute("href"));
    expect(hrefs[0]).toBe("/svc/x/overview");
    expect(hrefs[7]).toBe("/svc/x/approve-and-release");
    expect(new Set(hrefs).size).toBe(GENE_LABELS.length);
  });

  it("marks exactly the current section with aria-current=page", () => {
    render(<SectionBar current="review" hrefFor={hrefFor} />);
    const current = links().filter(
      (a) => a.getAttribute("aria-current") === "page",
    );
    expect(current).toHaveLength(1);
    expect(current[0].textContent).toBe("Review");
  });

  it("is links, not ARIA tabs", () => {
    const { container } = render(
      <SectionBar current="overview" hrefFor={hrefFor} />,
    );
    expect(links()).toHaveLength(GENE_LABELS.length);
    expect(
      container.querySelector(
        '[role="tab"], [role="tablist"], [aria-selected]',
      ),
    ).toBeNull();
  });

  it("leaves out an omitted section (CSF and ZT fold Inputs into AI draft)", () => {
    render(
      <SectionBar current="overview" hrefFor={hrefFor} omit={["inputs"]} />,
    );
    const shown = labels();
    expect(shown).toContain("AI draft");
    expect(shown).not.toContain("Inputs");
    expect(shown).toHaveLength(GENE_LABELS.length - 1);
  });

  it('names the nav "Service sections" (ruling, #736 issuecomment-6116092992)', () => {
    render(<SectionBar current="overview" hrefFor={hrefFor} />);
    expect(screen.getByRole("navigation")).toHaveAttribute(
      "aria-label",
      "Service sections",
    );
  });
});

describe("SectionBar degenerate states (for #1087)", () => {
  it("refuses a current section that is omitted", () => {
    expect(() =>
      render(
        <SectionBar current="inputs" hrefFor={hrefFor} omit={["inputs"]} />,
      ),
    ).toThrow(/current section "inputs" is omitted/);
  });

  // `current` is always one of the nine keys, so omitting every key always
  // omits the current one: that single check covers this state.
  it("refuses omitting every section", () => {
    const all: SectionKey[] = [
      "overview",
      "inputs",
      "ai-draft",
      "review",
      "analysis",
      "generate",
      "quality-check",
      "approve-and-release",
      "recommendations",
    ];
    expect(() =>
      render(<SectionBar current="overview" hrefFor={hrefFor} omit={all} />),
    ).toThrow(/omitted/);
    // The boundary: every key but the current one omitted still renders.
    render(
      <SectionBar
        current="overview"
        hrefFor={hrefFor}
        omit={all.filter((k) => k !== "overview")}
      />,
    );
    expect(links()).toHaveLength(1);
  });

  it("refuses an empty href", () => {
    expect(() =>
      render(
        <SectionBar
          current="overview"
          hrefFor={(k) => (k === "review" ? "" : `/svc/x/${k}`)}
        />,
      ),
    ).toThrow(/hrefFor\("review"\) returned an empty href/);
  });
});
