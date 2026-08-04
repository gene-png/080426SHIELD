import { proxyJsonFromRequest } from "../../../../_proxy";

export async function PUT(
  request: Request,
  props: { params: Promise<{ id: string; code: string }> },
) {
  const params = await props.params;
  return proxyJsonFromRequest(
    request,
    `/csf/services/${params.id}/gap-actions/${params.code}`,
    "PUT",
  );
}
