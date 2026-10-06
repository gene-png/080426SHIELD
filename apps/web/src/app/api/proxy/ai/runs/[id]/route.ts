import { proxyAiGet } from "../../_proxy";

export async function GET(
  _request: Request,
  props: { params: Promise<{ id: string }> },
) {
  const params = await props.params;
  return proxyAiGet(`/ai-runs/${params.id}`);
}
