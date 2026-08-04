import { proxyJson } from "../../../../_proxy";

export async function GET(
  _request: Request,
  props: { params: Promise<{ cid: string }> },
) {
  const params = await props.params;
  return proxyJson(`/risk/clients/${params.cid}/register/latest`, {
    method: "GET",
  });
}
