import { proxyJson } from "../../../_proxy";

export async function GET(
  request: Request,
  props: { params: Promise<{ id: string }> },
) {
  const params = await props.params;
  const incoming = new URL(request.url).searchParams.toString();
  const upstream = `/zt/services/${params.id}/gap-analysis${incoming ? `?${incoming}` : ""}`;
  return proxyJson(upstream, { method: "GET" });
}
