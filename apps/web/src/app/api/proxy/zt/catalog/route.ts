import { proxyJson } from "../_proxy";

export async function GET(request: Request) {
  // Forward the framework query param.
  const incoming = new URL(request.url).searchParams.toString();
  const upstream = `/zt/catalog${incoming ? `?${incoming}` : ""}`;
  return proxyJson(upstream, { method: "GET" });
}
