import { proxyAiJson } from "../_proxy";

export async function POST(request: Request) {
  return proxyAiJson(request, "/ai/preview");
}
