import { proxyJsonFromRequest } from "../../../_proxy";

// #645: the body carries `serves`, the AI status the consultant acknowledged,
// so the api can refuse a run that would now go live (#504).
export async function POST(
  request: Request,
  props: { params: Promise<{ id: string }> },
) {
  const params = await props.params;
  return proxyJsonFromRequest(
    request,
    `/attack/services/${params.id}/run-ai`,
    "POST",
  );
}
