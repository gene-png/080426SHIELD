import { proxyJsonFromRequest } from "../../../_proxy";

// The body carries `serves`, as run-ai's does (#504).
export async function POST(
  request: Request,
  props: { params: Promise<{ id: string }> },
) {
  const params = await props.params;
  return proxyJsonFromRequest(
    request,
    `/attack/scenarios/${params.id}/run`,
    "POST",
  );
}
