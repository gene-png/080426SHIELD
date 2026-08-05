import { proxyJsonFromRequest } from "../../../_proxy";

/**
 * Name the capabilities inside a bundled licence (UX finding 5). The consultant
 * supplies the component names; the model is never asked what a bundle contains.
 */
export async function POST(
  request: Request,
  props: { params: Promise<{ id: string }> },
) {
  const params = await props.params;
  return proxyJsonFromRequest(
    request,
    `/tech-debt/capability-items/${params.id}/components`,
    "POST",
  );
}
