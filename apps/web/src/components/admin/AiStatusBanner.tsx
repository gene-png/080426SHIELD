"use client";
import Link from "next/link";
import * as React from "react";

import { useAiStatus } from "@/lib/admin/aiStatus";

import type { JSX } from "react";

/**
 * Issue 2: warn an admin — on every admin page, including right after sign-in —
 * that AI will produce offline (fixture) output, and point at the fix.
 *
 * Previously this rendered on exactly one of the five workspaces and offered no
 * way to resolve the problem, so an admin could work for a whole session
 * without learning that every "Run AI" result was canned.
 *
 * Renders nothing while loading or when AI is ready, so a correctly configured
 * deployment sees no chrome at all.
 */
export function AiStatusBanner(): JSX.Element | null {
  const { status } = useAiStatus();

  if (!status || status.ready) return null;

  return (
    <div
      role="status"
      className="flex flex-wrap items-center gap-x-3 gap-y-2 rounded-md border border-status-warning-border bg-status-warning-bg px-4 py-3 text-sm text-status-warning-fg"
    >
      <span>
        <span className="font-semibold">AI is not live.</span> {status.detail}
      </span>
      {status.can_configure ? (
        <Link
          href="/admin/management#ai-provider-key"
          className="rounded-md border border-status-warning-border bg-surface-card px-3 py-1 text-xs font-semibold text-ink-primary hover:bg-surface-sunken"
        >
          Load an API key
        </Link>
      ) : null}
    </div>
  );
}
