import { proxyJson } from "../../../_proxy";

export async function GET(
  request: Request,
  props: { params: Promise<{ id: string }> },
) {
  const params = await props.params;
  // Pass query params through so target_tier + top_n reach the upstream.
  const incoming = new URL(request.url).searchParams.toString();
  const upstream = `/csf/services/${params.id}/gap-analysis${
    incoming ? `?${incoming}` : ""
  }`;
  return proxyJson(upstream, { method: "GET" });
}
