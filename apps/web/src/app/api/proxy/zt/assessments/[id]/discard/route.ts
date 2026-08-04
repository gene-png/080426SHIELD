import { proxyJson } from "../../../_proxy";

export async function POST(
  _request: Request,
  props: { params: Promise<{ id: string }> },
) {
  const params = await props.params;
  return proxyJson(`/zt/assessments/${params.id}/discard`, { method: "POST" });
}
