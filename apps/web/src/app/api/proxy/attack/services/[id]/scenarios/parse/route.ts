import { proxyJsonFromRequest } from "../../../../_proxy";

// #802: the chat box. The api proposes a change list from the text, by the
// slice C matcher or, where `serves` is "live", the AI reading; the body is
// `{text, serves}`. An AI attempt writes its llm_calls row and a counts-only
// audit entry; nothing else is stored.
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
