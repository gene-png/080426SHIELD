import { proxyJsonFromRequest } from "../../../_proxy";

export async function POST(
  request: Request,
  props: { params: Promise<{ id: string }> },
) {
  const params = await props.params;
  return proxyJsonFromRequest(
    request,
    `/tech-debt/capability-lists/${params.id}/approve`,
    "POST",
  );
}
