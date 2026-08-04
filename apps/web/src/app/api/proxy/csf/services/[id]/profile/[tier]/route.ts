import { proxyJson } from "../../../../_proxy";

export async function GET(
  _request: Request,
  props: { params: Promise<{ id: string; tier: string }> },
) {
  const params = await props.params;
  return proxyJson(`/csf/services/${params.id}/profile/${params.tier}`, {
    method: "GET",
  });
}
