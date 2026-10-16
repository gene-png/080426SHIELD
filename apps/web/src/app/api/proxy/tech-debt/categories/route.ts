import { proxyJson } from "../_proxy";

// #1176: the category dropdown's options (`tech_debt/extract.py` CATEGORIES).
export async function GET() {
  return proxyJson("/tech-debt/categories", { method: "GET" });
}
