import { proxyJsonFromRequest } from "../../../../_proxy";

/** Overturn a negative classification: this capability IS security-related. */
export async function POST(
  request: Request,
  props: { params: Promise<{ id: string }> },
) {
  const params = await props.params;
  return proxyJsonFromRequest(
    request,
    `/tech-debt/capability-items/${params.id}/security-classification/override`,
    "POST",
  );
}
