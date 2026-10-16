import { proxyJsonFromRequest } from "../../../../../_proxy";

// #1174: confirm many negative security classifications at once.
export async function POST(
  request: Request,
  props: { params: Promise<{ id: string }> },
) {
  const params = await props.params;
  return proxyJsonFromRequest(
    request,
    `/tech-debt/capability-lists/${params.id}/items/security-classification/confirm`,
    "POST",
  );
}
