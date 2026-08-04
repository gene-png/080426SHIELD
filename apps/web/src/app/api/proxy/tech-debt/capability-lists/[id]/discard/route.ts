import { proxyJson } from "../../../_proxy";

export async function POST(
  _request: Request,
  props: { params: Promise<{ id: string }> },
) {
  const params = await props.params;
  return proxyJson(`/tech-debt/capability-lists/${params.id}/discard`, {
    method: "POST",
  });
}
