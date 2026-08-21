/**
 * POST /api/proxy/attack/coverage/:id/confirm-citations - vouch for one
 * technique's inferred citations so its status may score again (#101 / #102).
 *
 * A missing proxy route is why the technique panel's edits were dead in the
 * browser once before (see ../route.ts). Added with the action rather than
 * after it.
 */
import { proxyJsonFromRequest } from "../../../_proxy";

export async function POST(
  request: Request,
  props: { params: Promise<{ id: string }> },
) {
  const params = await props.params;
  return proxyJsonFromRequest(
    request,
    `/attack/coverage/${params.id}/confirm-citations`,
    "POST",
  );
}
