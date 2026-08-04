import { proxyJson } from "../../../../_proxy";

export async function GET(
  _request: Request,
  props: { params: Promise<{ id: string }> },
) {
  const params = await props.params;
  return proxyJson(`/zt/services/${params.id}/assessments/latest`, {
    method: "GET",
  });
}
