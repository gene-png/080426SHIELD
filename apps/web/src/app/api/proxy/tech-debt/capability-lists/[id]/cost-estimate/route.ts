import { proxyJsonFromRequest } from "../../../../_proxy";

// TD-5 (for #1060): starts a Run-AI, so it forwards the body (`serves`).
export async function POST(
  request: Request,
  props: { params: Promise<{ id: string }> },
) {
  const params = await props.params;
  return proxyJsonFromRequest(
    request,
    `/tech-debt/capability-lists/${params.id}/cost-estimate`,
    "POST",
  );
}
