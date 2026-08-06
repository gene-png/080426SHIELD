import { proxyJsonFromRequest } from "../../../../_proxy";

/**
 * Agree that a capability is not security-related.
 *
 * Until a consultant signs off, the model's negative is provisional and the row
 * stays in the ATT&CK subset — a security tool wrongly dropped there cannot be
 * cited at all, so its absence reads as an assessed gap.
 */
export async function POST(
  request: Request,
  props: { params: Promise<{ id: string }> },
) {
  const params = await props.params;
  return proxyJsonFromRequest(
    request,
    `/tech-debt/capability-items/${params.id}/security-classification/confirm`,
    "POST",
  );
}
