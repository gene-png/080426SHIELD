import { proxyJson, proxyJsonFromRequest } from "../../../_proxy";

// #802: the service's what-ifs, and the base a new one would compare with.
export async function GET(
  _request: Request,
  props: { params: Promise<{ id: string }> },
) {
  const params = await props.params;
  return proxyJson(`/attack/services/${params.id}/scenarios`);
}

// #802: start a what-if; the body is `{removed: [...]}`.
export async function POST(
  request: Request,
  props: { params: Promise<{ id: string }> },
) {
  const params = await props.params;
  return proxyJsonFromRequest(
    request,
    `/attack/services/${params.id}/scenarios`,
    "POST",
  );
}
