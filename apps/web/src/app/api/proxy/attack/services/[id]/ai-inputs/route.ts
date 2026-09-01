import { proxyJson } from "../../../_proxy";

export async function GET(
  _request: Request,
  props: { params: Promise<{ id: string }> },
) {
  const params = await props.params;
  return proxyJson(`/attack/services/${params.id}/ai-inputs`, {
    method: "GET",
  });
}
