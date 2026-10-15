import { proxyJsonFromRequest } from "../../../../../_proxy";

/** #1120: "Start a revision" of one approved or released assessment. */
export async function POST(
  request: Request,
  props: { params: Promise<{ id: string; assessmentId: string }> },
) {
  const params = await props.params;
  return proxyJsonFromRequest(
    request,
    `/zt/services/${params.id}/assessments/${params.assessmentId}/revisions`,
    "POST",
  );
}
