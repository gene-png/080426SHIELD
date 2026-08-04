import { proxyJsonFromRequest } from "../../_proxy";

export async function PATCH(
  request: Request,
  props: { params: Promise<{ id: string }> },
) {
  const params = await props.params;
  return proxyJsonFromRequest(request, `/zt/answers/${params.id}`, "PATCH");
}
