import { expect, test } from "@playwright/test";

import { ADMIN_EMAIL, ADMIN_PASSWORD, signIn } from "../helpers/auth";
import { acknowledgeOfflineAi } from "../helpers/ai";
import { adminApiToken, API_BASE, atlasClientIdViaApi } from "../helpers/ids";

/**
 * #802 slice A: the ATT&CK what-if. The spec mints its OWN confirmed (R3)
 * base through the admin API -- a fresh service, two techniques with all three
 * capabilities in place, approved -- rather than relying on seeded data,
 * whose state other specs change.
 *
 * The prompt ships (#802), so the journey runs the analysis: the change list,
 * the affected count, the run control, a run to completion on the fixture-mode
 * answer (`attack_scenario_delta` in `app/ai/fixtures.py`), and a discard.
 */

const DETECT = "E2E What-if Detect Tool";
const PREVENT = "E2E What-if Prevent Tool";
const RESPOND = "E2E What-if Respond Tool";

test("an admin starts and discards an ATT&CK what-if against a confirmed assessment", async ({
  page,
  request,
}) => {
  const token = await adminApiToken(request);
  const clientId = await atlasClientIdViaApi(request, token);
  const H = { Authorization: `Bearer ${token}`, "X-Client-Id": clientId };

  const svc = await (
    await request.post(`${API_BASE}/attack/services`, {
      headers: H,
      data: { kind: "attack_coverage", title: "E2E ATT&CK What-if" },
    })
  ).json();
  const serviceId = svc.id as string;
  const assess = await (
    await request.post(`${API_BASE}/attack/services/${serviceId}/assessments`, {
      headers: H,
    })
  ).json();
  // STANDALONE techniques (D-094: a parent's status is computed).
  const all = assess.coverage as { id: string; technique_code: string }[];
  const standalone = all.filter(
    (c) =>
      !c.technique_code.includes(".") &&
      !all.some((o) => o.technique_code.startsWith(`${c.technique_code}.`)),
  );
  for (const row of standalone.slice(0, 2)) {
    const res = await request.patch(`${API_BASE}/attack/coverage/${row.id}`, {
      headers: H,
      data: {
        status: "covered",
        detection_tools: [DETECT],
        prevention_tools: [PREVENT],
        response_tools: [RESPOND],
      },
    });
    expect(res.ok(), await res.text()).toBe(true);
  }
  const approved = await request.post(
    `${API_BASE}/attack/assessments/${assess.id}/approve`,
    { headers: H },
  );
  expect(approved.ok(), await approved.text()).toBe(true);
  // The precondition, asserted rather than assumed: the api names this
  // assessment as the base a what-if compares with.
  const listed = await (
    await request.get(`${API_BASE}/attack/services/${serviceId}/scenarios`, {
      headers: H,
    })
  ).json();
  expect(listed.base?.assessment_id).toBe(assess.id);

  await signIn(page, ADMIN_EMAIL, ADMIN_PASSWORD);
  await page.goto(`/admin/services/${serviceId}/attack-coverage`);

  const panel = page.getByTestId("attack-scenario-panel");
  await expect(
    panel.getByRole("heading", { name: "ATT&CK what-if" }),
  ).toBeVisible();
  await expect(
    panel.getByText(/^Compared with the last confirmed assessment: version 1,/),
  ).toBeVisible();

  await panel.getByLabel(DETECT).check();
  await panel.getByRole("button", { name: "Continue" }).click();

  await expect(panel.getByTestId("attack-scenario-affected")).toHaveText(
    "2 techniques use these tools and will be re-assessed.",
  );
  const run = panel.getByRole("button", {
    name: "Run AI analysis on these changes",
  });
  await expect(run).toBeVisible();
  await run.click();
  // The offline guard intercepts the first click in fixture mode (CI, dev).
  await acknowledgeOfflineAi(page);
  // Completed: the after-rollup renders only once a run has finished. Then the
  // failure line's absence, which means something only after that.
  await expect(panel.getByTestId("scenario-after")).toBeVisible({
    timeout: 60_000,
  });
  await expect(panel.getByTestId("attack-scenario-run-failed")).toHaveCount(0);
  await expect(panel.getByTestId("attack-scenario-unavailable")).toHaveCount(0);

  await panel.getByRole("button", { name: "Discard this what-if" }).click();
  // The api's answer first (a positive state), then the control's absence.
  await expect
    .poll(async () => {
      const after = await (
        await request.get(
          `${API_BASE}/attack/services/${serviceId}/scenarios`,
          { headers: H },
        )
      ).json();
      return after.scenarios.map((s: { state: string }) => s.state);
    })
    .toEqual(["discarded"]);
  await expect(
    panel.getByRole("button", { name: "Discard this what-if" }),
  ).toHaveCount(0);
});
