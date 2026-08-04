import { proxyJson } from "../_proxy";

export async function GET() {
  return proxyJson("/attack/catalog", { method: "GET" });
}
