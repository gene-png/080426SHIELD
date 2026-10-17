"use client";
import { usePathname } from "next/navigation";

import { isWorkspace } from "@/components/admin/frameWidth";

import type { JSX } from "react";

/**
 * #1385: the body of one client's frame. The client's rail is the LEFT COLUMN
 * (flush to the edge, full height, under the admin top bar) and the page sits
 * beside it, with the padding and the readable cap the shell used to put around
 * the whole page. On narrow screens the rail stacks above the page.
 */
export function ClientFrameBody({
  rail,
  children,
}: {
  rail: React.ReactNode;
  children: React.ReactNode;
}): JSX.Element {
  const pathname = usePathname() ?? "";
  return (
    <div className="flex flex-col md:min-h-[calc(100vh-8rem)] md:flex-row">
      <div
        data-testid="client-left-column"
        className="shrink-0 border-b border-border-subtle bg-surface-card px-4 py-6 md:w-64 md:border-b-0 md:border-r"
      >
        {rail}
      </div>
      <div
        data-testid="client-frame-page"
        className={
          "min-w-0 flex-1 px-6 py-8 " +
          (isWorkspace(pathname) ? "" : "max-w-6xl")
        }
      >
        {children}
      </div>
    </div>
  );
}
