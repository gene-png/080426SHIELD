import { proxyJson } from "../../../../_proxy";

export async function POST(
  _request: Request,
  props: { params: Promise<{ cid: string }> },
) {
  const params = await props.params;
  return proxyJson(`/risk/clients/${params.cid}/register/export`, {
    method: "POST",
  });
}
