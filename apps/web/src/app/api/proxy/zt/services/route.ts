import { proxyJsonFromRequest } from "../_proxy";

export async function POST(request: Request) {
  return proxyJsonFromRequest(request, "/zt/services", "POST");
}
