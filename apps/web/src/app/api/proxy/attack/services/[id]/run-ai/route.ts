import { proxyJson } from "../../../_proxy";

export async function POST(
  _request: Request,
  props: { params: Promise<{ id: string }> },
) {
  const params = await props.params;
  return proxyJson(`/attack/services/${params.id}/run-ai`, { method: "POST" });
}
