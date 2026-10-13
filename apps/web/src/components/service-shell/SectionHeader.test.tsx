import "@testing-library/jest-dom/vitest";

import { render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import type { SectionKey } from "./SectionBar";
import { SectionHeader, type Visibility } from "./SectionHeader";

// Gene's verbatim copy, written out here as the spec. Plan v2 rules 2 and 6
// (#736, issuecomment-6116093149), which supersede v1's "What this page is
// for": "What this section is for, in one plain sentence; What you can do
// here, in one to three short bullets; its visibility state".
const PURPOSE_LABEL = "What this section is for";
const CAN_DO_LABEL = "What you can do here";
const VISIBILITY: Record<Visibility, string> = {
  internal: "Internal only",
  "client-preview": "Client preview",
  released: "Released to client",
};

// The advisor's format for the released label (#736, issuecomment-6116519635):
// "Released to client: v{n}, {d Mon yyyy}".
const RELEASE = { version: 2, releasedAt: "2026-10-12T15:00:00Z" };
const RELEASED_TEXT = "Released to client: v2, 12 Oct 2026";

function renderHeader(
  visibility: Visibility = "internal",
  canDo: string[] = ["DO-ONE", "DO-TWO"],
  section: SectionKey = "overview",
  // null: no release at all (undefined would take the default).
  release: { version: number; releasedAt: string } | null = RELEASE,
) {
  return render(
    <SectionHeader
      section={section}
      release={release ?? undefined}
      title="Overview"
      purpose="PURPOSE-TEXT"
      canDo={canDo}
      visibility={visibility}
    />,
  );
}

describe("SectionHeader (for #1087)", () => {
  it("makes the title the page's h1", () => {
    renderHeader();
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
      /^Overview$/,
    );
  });

  it("pairs Gene's purpose label with the caller's sentence", () => {
    renderHeader();
    const term = screen.getByText(PURPOSE_LABEL);
    expect(term.tagName).toBe("DT");
    expect(term.nextElementSibling?.textContent).toBe("PURPOSE-TEXT");
    expect(screen.queryByText("What this page is for")).toBeNull();
  });

  it("lists what you can do here as bullets, in the caller's order", () => {
    renderHeader("internal", ["DO-ONE", "DO-TWO", "DO-THREE"]);
    const term = screen.getByText(CAN_DO_LABEL);
    expect(term.tagName).toBe("DT");
    const items = within(term.nextElementSibling as HTMLElement).getAllByRole(
      "listitem",
    );
    expect(items.map((li) => li.textContent)).toEqual([
      "DO-ONE",
      "DO-TWO",
      "DO-THREE",
    ]);
  });

  it.each([[[]], [["1", "2", "3", "4"]]])(
    "refuses %j: the plan allows one to three bullets",
    (canDo) => {
      expect(() => renderHeader("internal", canDo)).toThrow(
        /one to three bullets/,
      );
    },
  );

  it.each(Object.entries(VISIBILITY) as [Visibility, string][])(
    "labels visibility %s as %s, and shows no other label",
    (visibility, label) => {
      renderHeader(visibility);
      const badge = screen.getByTestId("section-visibility");
      expect(badge.textContent).toBe(
        visibility === "released" ? RELEASED_TEXT : label,
      );
      for (const other of Object.values(VISIBILITY)) {
        if (other !== label) expect(screen.queryByText(other)).toBeNull();
      }
    },
  );
});

describe("SectionHeader refuses a label it cannot honour (for #1087)", () => {
  it.each(["client-preview", "released"] as Visibility[])(
    "refuses %s on the admin-only Recommendations section",
    (visibility) => {
      expect(() =>
        renderHeader(visibility, ["DO-ONE"], "recommendations"),
      ).toThrow(/admin-only section "recommendations".*"internal"/);
    },
  );

  it("accepts internal on Recommendations", () => {
    renderHeader("internal", ["DO-ONE"], "recommendations");
    expect(screen.getByTestId("section-visibility").textContent).toBe(
      "Internal only",
    );
  });

  it("refuses an unknown visibility rather than rendering a blank pill", () => {
    expect(() => renderHeader("public" as unknown as Visibility)).toThrow(
      /unknown visibility "public"/,
    );
  });

  it("styles client preview with the info border token", () => {
    renderHeader("client-preview");
    expect(screen.getByTestId("section-visibility").className).toContain(
      "border-status-info-border",
    );
  });
});

describe("SectionHeader's released label (for #1087)", () => {
  // Run in a zone west of UTC, so a date read in the viewer's local time would
  // differ from the UTC date the label must show.
  let savedTz: string | undefined;
  beforeEach(() => {
    savedTz = process.env.TZ;
    process.env.TZ = "America/New_York";
  });
  afterEach(() => {
    if (savedTz === undefined) delete process.env.TZ;
    else process.env.TZ = savedTz;
  });

  it.each([
    ["2026-10-12T15:00:00Z", 2, "Released to client: v2, 12 Oct 2026"],
    // An instant, shown in UTC: late evening west of UTC is the next UTC day.
    // 12 Oct in America/New_York (the zone pinned above), 13 Oct in UTC.
    ["2026-10-12T22:30:00-04:00", 3, "Released to client: v3, 13 Oct 2026"],
    // Three-letter months always: en-GB Intl would write "Sept".
    ["2026-09-01T00:00:00Z", 1, "Released to client: v1, 1 Sep 2026"],
  ])("formats %s, v%s as %s", (releasedAt, version, text) => {
    renderHeader("released", ["DO-ONE"], "overview", { version, releasedAt });
    expect(screen.getByTestId("section-visibility").textContent).toBe(text);
  });

  it.each([
    ["no release", null],
    ["version 0", { version: 0, releasedAt: "2026-10-12T00:00:00Z" }],
    ["version 1.5", { version: 1.5, releasedAt: "2026-10-12T00:00:00Z" }],
  ])("refuses %s", (_name, release) => {
    expect(() =>
      renderHeader("released", ["DO-ONE"], "overview", release),
    ).toThrow(/needs the released version/);
  });

  it("refuses an unparseable release date", () => {
    expect(() =>
      renderHeader("released", ["DO-ONE"], "overview", {
        version: 2,
        releasedAt: "2026-13-45T00:00:00Z", // zoned, but no such day
      }),
    ).toThrow(/not a parseable instant/);
  });

  it("ignores the release on a non-released label", () => {
    renderHeader("client-preview");
    expect(screen.getByTestId("section-visibility").textContent).toBe(
      "Client preview",
    );
  });
});

describe("SectionHeader refuses blank text it would render (for #1087)", () => {
  it("refuses a blank purpose", () => {
    expect(() =>
      render(
        <SectionHeader
          section="overview"
          title="T"
          purpose="  "
          canDo={["DO"]}
          visibility="internal"
        />,
      ),
    ).toThrow(/blank purpose/);
  });

  it("refuses a blank title", () => {
    expect(() =>
      render(
        <SectionHeader
          section="overview"
          title=""
          purpose="P"
          canDo={["DO"]}
          visibility="internal"
        />,
      ),
    ).toThrow(/blank title/);
  });

  it("refuses a blank bullet", () => {
    expect(() => renderHeader("internal", ["DO-ONE", " "])).toThrow(
      /blank bullet/,
    );
  });

  it.each([
    "2026-10-12T23:30:00",
    "2026-10-12",
    "12-10-2026",
    "2026-10-12Z",
    "2026-10-12+05:30",
    "Oct 12 2026 +0000",
    // Lowercase t and z parse differently across engines.
    "2026-10-12t15:00:00z",
    "2026-10-12T15:00:00z",
  ])(
    "refuses a release instant with no zone, %s (it would parse in local time)",
    (releasedAt) => {
      expect(() =>
        renderHeader("released", ["DO-ONE"], "overview", {
          version: 2,
          releasedAt,
        }),
      ).toThrow(/no zone/);
    },
  );

  it.each([
    "2026-10-12T15:00:00Z",
    "2026-10-12T15:00:00.123Z",
    "2026-10-12T11:00:00-04:00",
    "2026-10-12T20:30:00+0530",
    // Seconds are optional.
    "2026-10-12T22:30Z",
  ])("accepts a zoned instant, %s", (releasedAt) => {
    renderHeader("released", ["DO-ONE"], "overview", {
      version: 2,
      releasedAt,
    });
    expect(screen.getByTestId("section-visibility").textContent).toBe(
      "Released to client: v2, 12 Oct 2026",
    );
  });
});

describe("SectionHeader requireText on a missing value (for #1087)", () => {
  it("refuses an undefined purpose by name, not with a TypeError", () => {
    expect(() =>
      render(
        <SectionHeader
          section="overview"
          title="T"
          purpose={undefined as never}
          canDo={["DO"]}
          visibility="internal"
        />,
      ),
    ).toThrow(/a blank purpose/);
  });
});

describe("SectionHeader release date on a missing value (for #1087)", () => {
  it.each([[null], [undefined]])(
    "refuses releasedAt %s by name, not with a TypeError",
    (releasedAt) => {
      expect(() =>
        renderHeader("released", ["DO-ONE"], "overview", {
          version: 2,
          releasedAt: releasedAt as never,
        }),
      ).toThrow(/a blank release date/);
    },
  );
});

describe("SectionHeader refuses duplicate bullets (round 6 review, for #1087)", () => {
  it.each([
    ["the same bullet twice", ["DO-ONE", "DO-ONE"]],
    ["bullets equal once trimmed", ["DO-ONE", " DO-ONE "]],
  ])("refuses %s", (_name, canDo) => {
    expect(() => renderHeader("internal", canDo)).toThrow(
      /duplicate bullet "DO-ONE"/,
    );
  });
});
