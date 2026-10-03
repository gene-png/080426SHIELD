/**
 * POST /api/proxy/attack/assessments/:id/computed-status-review -- record a
 * consultant's review of computed statuses that differ from the AI's (#554 R3).
 * The body is `{ codes }`: the techniques the review panel showed.
 */
import { proxyJsonFromRequest } from "../../../_proxy";

export async function POST(
  request: Request,
  props: { params: Promise<{ id: string }> },
) {
  const params = await props.params;
  return proxyJsonFromRequest(
    request,
    `/attack/assessments/${params.id}/computed-status-review`,
    "POST",
  );
}
