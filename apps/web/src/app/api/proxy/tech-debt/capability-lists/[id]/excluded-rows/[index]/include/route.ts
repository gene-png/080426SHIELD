import { proxyJsonFromRequest } from "../../../../../_proxy";

/** Include a row the extraction skipped (UX finding 4 review queue). */
export async function POST(
  request: Request,
  props: { params: Promise<{ id: string; index: string }> },
) {
  const params = await props.params;
  return proxyJsonFromRequest(
    request,
    `/tech-debt/capability-lists/${params.id}/excluded-rows/${params.index}/include`,
    "POST",
  );
}
