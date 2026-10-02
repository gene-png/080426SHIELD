import { proxyAiGet } from "../../../_proxy";

export async function GET(
  request: Request,
  props: { params: Promise<{ id: string }> },
) {
  const params = await props.params;
  // #271: `subject_id` scopes the past runs to the page's own assessment.
  const subject = new URL(request.url).searchParams.get("subject_id");
  const scope = subject ? `?subject_id=${encodeURIComponent(subject)}` : "";
  return proxyAiGet(`/ai-runs/services/${params.id}${scope}`);
}
