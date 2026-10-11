/**
 * #646: whether an assessment's AI suggestions came from a live model or
 * offline test data, as every surface states it. Decided by the API
 * (`app.mode_stamp.ai_mode_for`, one derivation for the workspace, the
 * dashboard and the deliverable) and carried with its own sentence, so no
 * screen re-derives the state or rewords it.
 */
export type AiSourceState = "live" | "fixture" | "mixed" | "none" | "unknown";

export interface AiSource {
  state: AiSourceState;
  sentence: string;
  live_runs: number;
  fixture_runs: number;
}

/** The states a reader must not take AI-drafted values as analysis under. */
export function aiSourceIsWarning(source: AiSource): boolean {
  return source.state !== "live" && source.state !== "none";
}
