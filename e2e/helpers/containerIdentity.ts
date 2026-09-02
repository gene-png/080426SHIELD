/**
 * Fail an e2e run whose stack CHANGED UNDER IT.
 *
 * The shape this exists to catch is not a stale tree and not a skipped spec.
 * It is TWO VERSIONS IN ONE RUN, and the log afterwards looks completely
 * ordinary — some specs exercised the old code, some the new, and the summary
 * line reports a single verdict over both.
 *
 * How it happens here, observed 2026-09-02: the api container runs
 * `uvicorn --reload` over a bind mount, so an edit to `apps/api` is picked up
 * MID-RUN, while `apps/web` needs `docker compose up -d --force-recreate web`
 * and therefore keeps serving the old build. Edit both during a run and the
 * suite silently tests a combination that exists nowhere — a new backend
 * against an old frontend. Nothing errors. The report is green or red for
 * reasons unrelated to either version.
 *
 * A container id changes on `up --force-recreate`, `restart` (new id only on
 * recreate), a crash-and-restart, or a compose config change — every event that
 * means "the thing you started measuring is not the thing you finished
 * measuring". Uvicorn's in-process reload does NOT change the id, so this is a
 * floor rather than a complete guard: it catches the recreate half for certain
 * and is documented as not catching a pure in-process reload. Said plainly
 * because a guard whose limits are unstated is read as covering everything.
 *
 * Deliberately NOT a check that the ids match some expected value — there is no
 * such value. It records what was running at start and asserts the same thing
 * was running at end.
 */
import { execFileSync } from "node:child_process";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";

const SERVICES = ["api", "web"] as const;
const STAMP = join(__dirname, "..", ".playwright-container-ids.json");

type Ids = Record<string, string>;

function readIds(): Ids {
  const out: Ids = {};
  for (const svc of SERVICES) {
    // `compose ps -q` prints the container id, or nothing when it is not up.
    const id = execFileSync("docker", ["compose", "ps", "-q", svc], {
      cwd: join(__dirname, "..", ".."),
      encoding: "utf8",
      stdio: ["ignore", "pipe", "pipe"],
    }).trim();
    if (!id) {
      throw new Error(
        `container-identity: service "${svc}" is not running. ` +
          `Start the stack before the suite; a run against a half-up stack ` +
          `reports failures that say nothing about the code.`,
      );
    }
    out[svc] = id;
  }
  return out;
}

/** Record what is running. Fails closed: if it cannot look, it does not pass. */
export function captureContainerIds(): void {
  const ids = readIds();
  mkdirSync(dirname(STAMP), { recursive: true });
  writeFileSync(
    STAMP,
    JSON.stringify({ at: new Date().toISOString(), ids }, null, 2),
  );
  const summary = SERVICES.map((s) => `${s}=${ids[s].slice(0, 12)}`).join(" ");
  console.log(`container-identity: run starts against ${summary}`);
}

/** Assert the same containers are still running. Throws, so the run goes red. */
export function assertContainerIdsUnchanged(): void {
  let before: Ids;
  try {
    before = JSON.parse(readFileSync(STAMP, "utf8")).ids;
  } catch (err) {
    // "I could not look" must not share a branch with "nothing to complain
    // about" — the rule this repo has recorded four times in its own tooling.
    throw new Error(
      `container-identity: no start stamp to compare against (${String(err)}). ` +
        `The run cannot be certified; treat its result as unknown, not green.`,
    );
  }
  const after = readIds();
  const moved = SERVICES.filter((s) => before[s] !== after[s]);
  if (moved.length) {
    const detail = moved
      .map(
        (s) => `  ${s}: ${before[s].slice(0, 12)} -> ${after[s].slice(0, 12)}`,
      )
      .join("\n");
    throw new Error(
      `container-identity: the stack changed DURING this run.\n${detail}\n\n` +
        `Some specs ran against one version and some against another, so this ` +
        `run's verdict — pass OR fail — describes no single state of the code. ` +
        `Recreate the stack and run again; do not report this result.`,
    );
  }
  console.log("container-identity: same api and web containers throughout");
}
