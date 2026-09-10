/**
 * Refuse to start a run whose AI mode is not the one the run INTENDS.
 *
 * ## The failure this exists to prevent
 *
 * `kentro-demo-failed-items.md` item 2.2: deleting the credential row, or a
 * `docker compose down -v`, reverts the instance to fixture with **no
 * announcement**. "Deliberately configured fixture" and "had a key, lost it to
 * a volume wipe" render identically. The worst outcome available is recording
 * an entire take in fixture mode believing it is live — canned demo content
 * presented to a client as analysis of their own data.
 *
 * The remedy as written was a human remembering to check a badge before the
 * take. This converts it into a gate, on the same argument as
 * `containerIdentity`: a green from the wrong mode is indistinguishable from a
 * green from the right one, so you ask BEFORE starting rather than trusting
 * afterwards.
 *
 * ## Why it is symmetric
 *
 * Hardcoding "must be live" would refuse every Phase 1 rehearsal. So the run
 * DECLARES its intent and this refuses on any disagreement, in both
 * directions:
 *
 *   * A rehearsal intends `fixture`. A stack reporting live means the run
 *     would spend real tokens and cross the Phase 1 boundary — refuse.
 *   * A take intends `live`. A stack reporting fixture is item 2.2 — refuse.
 *
 * The second direction is the one 2.2 is about; the first makes "do not enable
 * live AI" mechanical for Phase 1 rather than a promise. Symmetric is strictly
 * stronger than either half.
 *
 * ## Why it reads `ready` and NOT `SHIELD_LLM_MODE`
 *
 * An env var cannot answer this question. `admin/ai-status`'s `_ai_readiness`
 * short-circuits on `if source != "database" and s.shield_llm_mode != "live"`
 * — so a key pasted through Admin → Management (source `database`) **skips the
 * mode check entirely** and forces live on the very next Run-AI with no
 * restart, while `SHIELD_LLM_MODE` still reads `fixture`. `keystore.load_key`
 * reads the `llm_credential` table only.
 *
 * `ready` is documented as "true only when a real provider call will be made",
 * which is the question being asked. `mode` and `key_source` are reported in
 * the failure message because they are what a human needs to fix it, but they
 * are NOT what the decision keys on.
 *
 * Note also that `keystore.effective_key()` falls back to the environment
 * while `load_key()` does not — so `effective_key` describes a key the run path
 * would not use. Anything built on it would be reporting about the wrong key.
 *
 * ## What is NOT exercised
 *
 * **The live branch has never been observed firing.** Proving it would mean
 * pasting an API key, which Phase 1 forbids. The refusal path is exercised
 * against a stubbed status object in `aiModeGate.test.ts`; against the running
 * stack only the `fixture`-intent-and-fixture-actual case has ever run. Said
 * plainly because a guard whose limits are unstated is read as covering
 * everything — the same caveat `containerIdentity` carries about in-process
 * reloads.
 */

export type AiMode = "fixture" | "live";

/** The shape this gate needs. A superset of it is what the endpoint returns. */
export interface AiStatus {
  ready?: unknown;
  mode?: unknown;
  provider?: unknown;
  model?: unknown;
  key_source?: unknown;
  detail?: unknown;
}

export class AiModeRefusal extends Error {}

/**
 * What this run intends, from `SHIELD_ENGAGEMENT_AI_MODE`.
 *
 * Defaults to `fixture` — the Phase 1 posture — so an operator who sets
 * nothing gets the safe intent rather than an unguarded run. A value that is
 * neither mode is a refusal, not a fallback to the default: "I could not read
 * the intent" and "the intent is fixture" must not be the same branch.
 */
export function intendedAiMode(env: NodeJS.ProcessEnv = process.env): AiMode {
  const raw = (env.SHIELD_ENGAGEMENT_AI_MODE ?? "fixture").trim().toLowerCase();
  if (raw !== "fixture" && raw !== "live") {
    throw new AiModeRefusal(
      `ai-mode-gate: SHIELD_ENGAGEMENT_AI_MODE=${JSON.stringify(raw)} is not ` +
        `"fixture" or "live". Refusing rather than guessing an intent — this ` +
        `gate exists to stop a run happening in a mode nobody chose.`,
    );
  }
  return raw;
}

/**
 * Decide the mode the stack will ACTUALLY run in, from a status payload.
 *
 * Fails closed on anything it cannot read. An unreadable status is not a
 * fixture status: "I could not look" and "nothing to complain about" must not
 * share a branch, which is this repo's most-repeated gate defect.
 */
export function actualAiMode(status: AiStatus): AiMode {
  if (status === null || typeof status !== "object") {
    throw new AiModeRefusal(
      `ai-mode-gate: /admin/ai-status did not return an object (got ` +
        `${typeof status}). Cannot determine the AI mode, so refusing to start.`,
    );
  }
  if (typeof status.ready !== "boolean") {
    throw new AiModeRefusal(
      `ai-mode-gate: /admin/ai-status has no boolean "ready" field ` +
        `(got ${JSON.stringify(status.ready)}). That field is the only ` +
        `truthful signal of whether a real provider call will be made, so ` +
        `refusing to start rather than inferring from "mode".`,
    );
  }
  return status.ready ? "live" : "fixture";
}

/** A one-line description for logs and failure messages. */
export function describeAiStatus(status: AiStatus): string {
  const bit = (k: keyof AiStatus) =>
    status[k] === undefined ? "?" : String(status[k]);
  return (
    `ready=${bit("ready")} mode=${bit("mode")} ` +
    `provider=${bit("provider")} model=${bit("model")} ` +
    `key_source=${bit("key_source")}`
  );
}

/**
 * Throw unless the stack's actual mode is the intended one.
 *
 * Separate from the fetching so the decision is testable without a browser,
 * and so the live branch can be exercised against a stubbed status.
 */
export function assertAiModeMatches(intended: AiMode, status: AiStatus): void {
  const actual = actualAiMode(status);
  if (actual === intended) return;

  const why =
    intended === "live"
      ? "This is failed-item 2.2: a wipe or a deleted credential row reverts " +
        "the stack to fixture SILENTLY, and canned output is indistinguishable " +
        "from analysis once it is on camera. Load a key through " +
        "Admin -> Management and confirm the badge before restarting."
      : "A rehearsal must not spend real tokens, and Phase 1's boundary is " +
        "that live AI stays off. Something has loaded a key — note that a key " +
        "in the database forces live REGARDLESS of SHIELD_LLM_MODE.";

  throw new AiModeRefusal(
    `ai-mode-gate: REFUSING TO START.\n` +
      `  intended: ${intended}   (SHIELD_ENGAGEMENT_AI_MODE)\n` +
      `  actual:   ${actual}\n` +
      `  status:   ${describeAiStatus(status)}\n` +
      `  detail:   ${status.detail === undefined ? "?" : String(status.detail)}\n\n` +
      `${why}`,
  );
}

/**
 * Fetch the status through an already-signed-in admin page and assert on it.
 *
 * Takes the page rather than creating its own session: the endpoint is
 * admin-only, and threading a second sign-in through here would double the
 * gate's cost for no gain.
 */
export async function assertAiMode(
  page: { request: { get(url: string): Promise<PlaywrightResponse> } },
  intended: AiMode,
): Promise<AiStatus> {
  const res = await page.request.get("/api/proxy/admin/ai-status");
  if (!res.ok()) {
    const body = await res.text().catch(() => "<unreadable>");
    throw new AiModeRefusal(
      `ai-mode-gate: GET /api/proxy/admin/ai-status -> ${res.status()}. ` +
        `Cannot establish the AI mode, so refusing to start — an unreadable ` +
        `status is NOT a fixture status.\n  body: ${body.slice(0, 400)}`,
    );
  }

  let status: AiStatus;
  try {
    status = (await res.json()) as AiStatus;
  } catch (err) {
    throw new AiModeRefusal(
      `ai-mode-gate: /admin/ai-status returned unparseable JSON (${String(err)}). ` +
        `Refusing to start.`,
    );
  }

  assertAiModeMatches(intended, status);
  // eslint-disable-next-line no-console
  console.log(
    `ai-mode-gate: intended=${intended}, ${describeAiStatus(status)}`,
  );
  return status;
}

interface PlaywrightResponse {
  ok(): boolean;
  status(): number;
  text(): Promise<string>;
  json(): Promise<unknown>;
}
