/**
 * PATCH /api/proxy/attack/coverage/:id - update one technique's coverage row
 * (status, notes, D/P/R tools, lock). Mirrors zt/answers/[id]. This route was
 * missing, which left the technique panel's edits (including the C2 lock
 * toggle) dead in the browser; found by e2e/smoke/s5-attack.spec.ts.
 */
import { proxyJsonFromRequest } from "../../_proxy";

export async function PATCH(request: Request, props: { params: Promise<{ id: string }> }) {
  const params = await props.params;
  return proxyJsonFromRequest(request, `/attack/coverage/${params.id}`, "PATCH");
}
