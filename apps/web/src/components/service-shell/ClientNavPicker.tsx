"use client";
import * as React from "react";
import { useRouter } from "next/navigation";

import { AdminClientPicker } from "@/components/admin/AdminClientPicker";
import { CLIENT_LINES } from "@/components/admin/ClientScopedPage";
import { resolveClientChoice, type ReadState } from "@/lib/admin/client-choice";
import { readClientList } from "@/lib/admin/client-reads";

import { clientHref } from "./frameRoutes";
import { SHELL_COPY } from "./shellCopy";

import type { JSX } from "react";

/**
 * T6: the frame's client picker. It reuses the admin client list and its
 * labels (`readClientList` + `resolveClientChoice`, RR-2) and the RR-2 picker
 * with its explicit Apply, and NAVIGATES to the chosen client's frame.
 *
 * It never reads or writes the active-client cookie (#1129's class): the
 * cookie read is passed as never-settled and the URL as PRESENT, a row of
 * `resolveClientChoice` that decides before it would ever consult the cookie.
 */
const COOKIE_NOT_CONSULTED: ReadState = { state: "pending" };

export function ClientNavPicker({
  currentId,
}: {
  currentId: string | null;
}): JSX.Element {
  const router = useRouter();
  const [list, setList] = React.useState<ReadState>({ state: "pending" });

  React.useEffect(() => {
    let active = true;
    readClientList().then(
      (value) => {
        if (active) setList({ state: "ok", value });
      },
      (err: unknown) => {
        console.error("[client_frame] client list read failed", err);
        if (active) setList({ state: "failed" });
      },
    );
    return () => {
      active = false;
    };
  }, []);

  const choice = resolveClientChoice(list, COOKIE_NOT_CONSULTED, {
    present: true,
    value: currentId ?? "",
  });
  if (choice.kind === "list_failed")
    return (
      <p className="text-xs text-status-danger-fg">{CLIENT_LINES.listFailed}</p>
    );
  if (choice.kind === "none")
    return <p className="text-xs text-ink-tertiary">{SHELL_COPY.pickerNone}</p>;

  const current = choice.kind === "chosen" ? choice.client : null;
  return (
    <AdminClientPicker
      key={`picker-${current?.id ?? choice.kind}`}
      clients={choice.kind === "loading" ? null : choice.clients}
      current={current}
      disabled={false}
      onApply={(client) => {
        console.info("[client_frame] picker opens", client.id);
        router.push(clientHref(client.id));
      }}
    />
  );
}
