import { proxyJson } from "../../../../_proxy";

/** POST /api/proxy/risk/clients/{cid}/register/publish (#737). */
export async function POST(
  _request: Request,
  props: { params: Promise<{ cid: string }> },
) {
  const params = await props.params;
  return proxyJson(`/risk/clients/${params.cid}/register/publish`, {
    method: "POST",
  });
}
