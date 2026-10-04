import { proxyJsonFromRequest } from "../../../../_proxy";

// #802 slice C: the chat box. The api proposes a change list from the text
// and writes nothing; the body is `{text}`.
export async function POST(
  request: Request,
  props: { params: Promise<{ id: string }> },
) {
  const params = await props.params;
  return proxyJsonFromRequest(
    request,
    `/attack/services/${params.id}/scenarios/parse`,
    "POST",
  );
}
