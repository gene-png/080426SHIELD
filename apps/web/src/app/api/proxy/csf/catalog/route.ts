import { proxyJson } from "../_proxy";

export async function GET() {
  return proxyJson("/csf/catalog", { method: "GET" });
}
