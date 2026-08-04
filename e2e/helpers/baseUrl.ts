import * as fs from "fs";
import * as path from "path";

/**
 * Resolve the web app's base URL for host-run e2e.
 *
 * Priority: E2E_BASE_URL env var > WEB_PORT in the repo-root .env (the same
 * machine-local file docker-compose reads to publish the web container on a
 * non-default host port) > the canonical http://localhost:3000.
 *
 * File-based on purpose: the sprint loop runs specs from fresh shells, so a
 * port override must not depend on per-shell env discipline. CI composes the
 * stack with no .env and stays on 3000.
 */
export function resolveBaseUrl(): string {
  if (process.env.E2E_BASE_URL) {
    return process.env.E2E_BASE_URL;
  }
  const envPath = path.resolve(__dirname, "..", "..", ".env");
  if (fs.existsSync(envPath)) {
    const match = fs
      .readFileSync(envPath, "utf8")
      .match(/^\s*WEB_PORT\s*=\s*(\d+)\s*$/m);
    if (match) {
      return `http://localhost:${match[1]}`;
    }
  }
  return "http://localhost:3000";
}
