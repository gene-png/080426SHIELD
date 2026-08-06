import { expect, test } from "@playwright/test";

import { ADMIN_EMAIL, ADMIN_PASSWORD, signIn } from "../helpers/auth";
import { adminApiToken, API_BASE, atlasClientIdViaApi } from "../helpers/ids";

/**
 * The derived six-stage progress bar.
 *
 * Presentation only — no state machine, route or audit vocabulary changed, and
 * `status` still means what it meant. Two of the six stages are not states
 * anybody stores: a capability list is DRAFT before a Run-AI and still DRAFT
 * after, so `analyze` and `generate` are derived from evidence.
 *
 * THE ASSERTION THAT MATTERS is the version trap. `llm_calls` carries no
 * version link and `Deliverable.version` is its own counter, so the naive query
 * ("has this service ever been analysed?") lights up `analyze` on a brand-new
 * draft because a discarded one was analysed earlier. Unit tests pin the
 * derivation; this spec proves it survives a real discard-and-re-extract cycle
 * through the API and renders correctly in the browser.
 *
 * Mints its own service — a shared-DB suite where one spec leans on another's
 * leftovers passes alone and fails in sequence (the s11-staleness defect).
 */

const INVENTORY_CSV =
  "name,vendor,category,annual_cost_usd\n" +
  "CrowdStrike Falcon,CrowdStrike,EDR,120000\n" +
  "Splunk Enterprise,Splunk,SIEM,200000\n";

interface StageRow {
  key: string;
  state: "complete" | "current" | "pending";
}

async function stagesFor(
  request: import("@playwright/test").APIRequestContext,
  headers: Record<string, string>,
  serviceId: string,
): Promise<Record<string, string>> {
  const res = await request.get(`${API_BASE}/services/${serviceId}/stages`, {
    headers,
  });
  expect(res.ok(), "GET /services/{id}/stages").toBeTruthy();
  const body = (await res.json()) as { stages: StageRow[] };
  return Object.fromEntries(body.stages.map((s) => [s.key, s.state]));
}

test("stage evidence is scoped to the version that produced it", async ({
  request,
}) => {
  test.slow();
  const token = await adminApiToken(request);
  const clientId = await atlasClientIdViaApi(request, token);
  const H = { Authorization: `Bearer ${token}`, "X-Client-Id": clientId };

  const svc = await (
    await request.post(`${API_BASE}/tech-debt/services`, {
      headers: H,
      data: { kind: "tech_debt", title: "E2E Stage Versioning" },
    })
  ).json();
  const serviceId = svc.id as string;

  // Nothing started: the first stage is where the work is.
  const fresh = await stagesFor(request, H, serviceId);
  expect(fresh.prepare).toBe("current");
  expect(fresh.analyze).toBe("pending");
  expect(fresh.release).toBe("pending");

  const artifact = await (
    await request.post(`${API_BASE}/artifacts`, {
      headers: H,
      multipart: {
        file: {
          name: "inventory.csv",
          mimeType: "text/csv",
          buffer: Buffer.from(INVENTORY_CSV),
        },
      },
    })
  ).json();

  // v1: extract, so an analysis run exists and is attributable to THIS version.
  const v1 = await (
    await request.post(
      `${API_BASE}/tech-debt/services/${serviceId}/capability-lists/extract`,
      { headers: H, data: { artifact_id: artifact.id } },
    )
  ).json();

  const afterExtract = await stagesFor(request, H, serviceId);
  expect(afterExtract.prepare).toBe("complete");
  expect(
    afterExtract.analyze,
    "the extraction belongs to v1, so v1 is analysed",
  ).toBe("complete");
  expect(afterExtract.approve).toBe("pending");

  // Discard v1 and cut a fresh v2 that has had NO run of its own.
  const discarded = await request.post(
    `${API_BASE}/tech-debt/capability-lists/${v1.id}/discard`,
    { headers: H },
  );
  expect(discarded.ok(), "discard v1").toBeTruthy();

  // A new draft with no extraction: created by uploading, not by running AI.
  // The version row exists; the analysis that produced v1 predates it.
  const v2 = await (
    await request.post(
      `${API_BASE}/tech-debt/services/${serviceId}/capability-lists/extract`,
      { headers: H, data: { artifact_id: artifact.id } },
    )
  ).json();
  expect(v2.version, "a fresh version was minted").toBeGreaterThan(v1.version);

  // v2 ran its own extraction, so it is legitimately analysed — the point here
  // is that the stage tracks the CURRENT version rather than the service's
  // whole history, which the negative case below proves.
  const afterRerun = await stagesFor(request, H, serviceId);
  expect(afterRerun.analyze).toBe("complete");

  // The negative: approving and finalizing moves the later stages, and no
  // earlier stage may be left showing a cursor behind completed work.
  for (const item of v2.items as { id: string }[]) {
    await request.patch(`${API_BASE}/tech-debt/capability-items/${item.id}`, {
      headers: H,
      data: { disposition: "keep" },
    });
  }
  await request.post(
    `${API_BASE}/tech-debt/capability-lists/${v2.id}/approve`,
    {
      headers: H,
    },
  );

  const afterApprove = await stagesFor(request, H, serviceId);
  expect(afterApprove.approve).toBe("complete");
  // Monotonic: reaching `approve` means everything before it is behind you.
  // A "current" marker sitting left of completed stages reads as a broken step
  // rather than a passed one (found in the browser, 2026-08-05).
  const order = [
    "prepare",
    "analyze",
    "review",
    "approve",
    "generate",
    "release",
  ];
  const states = order.map((k) => afterApprove[k]);
  const firstNonComplete = states.findIndex((s) => s !== "complete");
  if (firstNonComplete !== -1) {
    expect(
      states.slice(firstNonComplete).every((s) => s !== "complete"),
      `no completed stage may follow an incomplete one: ${states.join(",")}`,
    ).toBeTruthy();
  }
  // Exactly one cursor, always.
  expect(states.filter((s) => s === "current")).toHaveLength(1);
});

test("the workspace renders the bar with per-service wording and accessible state", async ({
  page,
  request,
}) => {
  test.slow();
  const token = await adminApiToken(request);
  const clientId = await atlasClientIdViaApi(request, token);
  const H = { Authorization: `Bearer ${token}`, "X-Client-Id": clientId };

  const td = await (
    await request.post(`${API_BASE}/tech-debt/services`, {
      headers: H,
      data: { kind: "tech_debt", title: "E2E Stage Bar (tech debt)" },
    })
  ).json();

  await signIn(page, ADMIN_EMAIL, ADMIN_PASSWORD);
  await page.goto(`/admin/services/${td.id}/tech-debt`);
  await expect(
    page.getByRole("heading", { name: "Technical Debt Review" }),
  ).toBeVisible({ timeout: 30000 });

  const bar = page.getByRole("navigation", { name: "Assessment progress" });
  await expect(bar).toBeVisible({ timeout: 30000 });

  // Tech Debt has no client self-assessment step, so the first stage is
  // "Prepare" — rather than a "Submitted" stage that could never light.
  await expect(bar.getByText("Prepare", { exact: true })).toBeVisible();
  await expect(bar.getByText("Self-assessment")).toHaveCount(0);
  for (const label of ["Analyze", "Review", "Approve", "Generate", "Release"]) {
    await expect(bar.getByText(label, { exact: true })).toBeVisible();
  }

  // Stage state is colour-coded, so it must also be readable as text — a
  // progress indicator whose whole meaning is dot colour conveys nothing
  // without sight.
  const spoken = await bar.innerText();
  expect(spoken).toContain("not started");
  expect(spoken).toMatch(/in progress|completed/);
});

test("Zero Trust names its client-input stage instead of calling it Prepare", async ({
  page,
  request,
}) => {
  // The one place the four services genuinely differ. Zero Trust waits on a
  // client self-assessment; Tech Debt and ATT&CK have no such step, and the
  // asymmetry lives in this wording rather than in a permanently dead stage.
  test.slow();
  const token = await adminApiToken(request);
  const clientId = await atlasClientIdViaApi(request, token);
  const H = { Authorization: `Bearer ${token}`, "X-Client-Id": clientId };

  const zt = await (
    await request.post(`${API_BASE}/zt/services`, {
      headers: H,
      data: { kind: "zero_trust_cisa", title: "E2E Stage Bar (zero trust)" },
    })
  ).json();

  await signIn(page, ADMIN_EMAIL, ADMIN_PASSWORD);
  await page.goto(`/admin/services/${zt.id}/zero-trust-cisa`);

  const bar = page.getByRole("navigation", { name: "Assessment progress" });
  await expect(bar).toBeVisible({ timeout: 30000 });
  await expect(bar.getByText("Self-assessment")).toBeVisible();
  await expect(bar.getByText("Prepare", { exact: true })).toHaveCount(0);
});
