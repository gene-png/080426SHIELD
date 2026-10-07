import "@testing-library/jest-dom/vitest";

import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import * as riskClient from "@/lib/risk/client";
import type { RiskDuplicateService } from "@/lib/risk/types";

import {
  ArchiveServiceButton,
  ArchiveServiceDialog,
} from "./ArchiveServiceButton";

/**
 * #896: one archive button per duplicate service on the Risk Register's
 * duplicate banner, and one confirm dialog in the `DiscardDraftButton`
 * pattern. Review B2 (advisor, #736 6046491381): the dialog archives through
 * the Risk-scoped route and reloads the gate on ANY outcome; on failure it
 * stays open with the message, because the reload may remove the very button
 * that opened it.
 *
 * Every string is copied from the advisor's approvals (#736 6042801745 and
 * 6046491381), never from the component.
 */

vi.mock("@/lib/risk/client", () => ({ archiveDuplicateService: vi.fn() }));

const archive = vi.mocked(riskClient.archiveDuplicateService);

// jsdom does not implement <dialog>.showModal()/.close() (see
// DiscardDraftButton.test.tsx).
beforeAll(() => {
  HTMLDialogElement.prototype.showModal = function showModal(): void {
    this.open = true;
  };
  HTMLDialogElement.prototype.close = function close(): void {
    this.open = false;
    this.dispatchEvent(new Event("close"));
  };
});

const BODY =
  "The Risk Register will stop drawing on ZT 2: the next version you generate leaves out its findings, and publishing no longer waits for it. Nothing else changes: its assessments, its deliverables and the client's view of it stay as they are. Archiving cannot be undone.";
const FALLBACK = "The service could not be archived. Nothing was changed.";
// The server's sentence and the screen's two lines, from the advisor's
// rulings (#736 6046491381 as amended by 6047873969), written out by hand.
const NOT_IN_GROUP =
  "ZT 2 is no longer one of several engaged services of the same kind, so it was not archived.";
const REFRESHED = "The list has been refreshed.";
const NOT_REFRESHED =
  "The list could not be refreshed. Reload the page before trying again.";
const UNKNOWN =
  "We couldn't confirm whether this finished. It may still complete; check before trying again.";

// The advisor's line (#736 6046898402) for SVC below, written out by hand.
const LINE = "Started 3 Oct 2026, version 1, in progress (draft)";

const SVC: RiskDuplicateService = {
  service_id: "svc-2",
  title: "ZT 2",
  started_at: "2026-10-03T12:00:00Z",
  status: "draft",
  version: 1,
};

function setup(
  service: RiskDuplicateService | null = SVC,
  reloaded: boolean = true,
) {
  const onClose = vi.fn();
  const onSettled = vi.fn().mockResolvedValue(reloaded);
  const { container, rerender } = render(
    <ArchiveServiceDialog
      clientId="c1"
      service={service}
      onClose={onClose}
      onSettled={onSettled}
    />,
  );
  const dialog = container.querySelector("dialog") as HTMLDialogElement;
  return { dialog, onClose, onSettled, rerender };
}

async function confirm(dialog: HTMLDialogElement): Promise<void> {
  await act(async () => {
    fireEvent.click(
      within(dialog).getByRole("button", { name: "Yes, archive" }),
    );
  });
}

describe("ArchiveServiceButton (#896)", () => {
  it("names the service and reports which one was asked for", () => {
    const onOpen = vi.fn();
    render(<ArchiveServiceButton service={SVC} onOpen={onOpen} />);
    fireEvent.click(screen.getByRole("button", { name: "Archive ZT 2" }));
    expect(onOpen).toHaveBeenCalledWith(SVC);
  });

  it("carries the approved line beneath it, describing the button", () => {
    render(<ArchiveServiceButton service={SVC} onOpen={vi.fn()} />);
    const button = screen.getByRole("button", { name: "Archive ZT 2" });
    expect(screen.getByText(LINE)).toBeInTheDocument();
    expect(button).toHaveAccessibleDescription(LINE);
  });
});

describe("ArchiveServiceDialog (#896)", () => {
  beforeEach(() => {
    archive.mockReset();
  });

  it("is closed while no service is chosen", () => {
    const { dialog } = setup(null);
    expect(dialog.open).toBe(false);
  });

  it("names the service, with the approved body", () => {
    const { dialog } = setup();
    expect(dialog.open).toBe(true);
    expect(
      within(dialog).getByRole("heading", { name: "Archive ZT 2?" }),
    ).toBeInTheDocument();
    expect(within(dialog).getByText(BODY)).toBeInTheDocument();
    expect(archive).not.toHaveBeenCalled();
  });

  it("shows the approved line under its title", () => {
    const { dialog } = setup();
    expect(within(dialog).getByText(LINE)).toBeInTheDocument();
  });

  it("archives nothing when cancelled", () => {
    const { dialog, onClose, onSettled } = setup();
    fireEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(onClose).toHaveBeenCalledTimes(1);
    expect(archive).not.toHaveBeenCalled();
    expect(onSettled).not.toHaveBeenCalled();
  });

  it("archives that service through the client's route, reloads, and closes", async () => {
    archive.mockResolvedValue(undefined);
    const { dialog, onClose, onSettled } = setup();
    await confirm(dialog);
    expect(archive).toHaveBeenCalledWith("c1", "svc-2");
    expect(onSettled).toHaveBeenCalledTimes(1);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("says Archiving… while the archive is in flight", async () => {
    archive.mockReturnValue(new Promise(() => {}));
    const { dialog } = setup();
    await confirm(dialog);
    expect(
      within(dialog).getByRole("button", { name: "Archiving…" }),
    ).toBeDisabled();
    expect(
      within(dialog).getByRole("button", { name: "Cancel" }),
    ).toBeDisabled();
  });

  // Review round 2, F1 (advisor, #736 6047873969): the server's refusal no
  // longer claims a refresh; the SCREEN appends one line, chosen by whether
  // the gate reload after the failure succeeded. Same for the 504.
  const REFUSAL = {
    status: 409,
    payload: {
      error: {
        code: 409,
        reason: "service_not_in_duplicate_group",
        message: NOT_IN_GROUP,
      },
    },
  };
  const UNKNOWN_504 = {
    status: 504,
    payload: {
      error: {
        code: 504,
        reason: "upstream_outcome_unknown",
        message: UNKNOWN,
      },
    },
  };

  it("on the server's refusal, after a successful reload, says the list was refreshed", async () => {
    archive.mockRejectedValue(REFUSAL);
    const { dialog, onClose, onSettled } = setup(SVC, true);
    await confirm(dialog);
    expect(within(dialog).getByRole("alert").textContent).toBe(
      `${NOT_IN_GROUP} ${REFRESHED}`,
    );
    expect(onSettled).toHaveBeenCalledTimes(1);
    expect(onClose).not.toHaveBeenCalled();
    expect(dialog.open).toBe(true);
  });

  it("on the server's refusal, after a FAILED reload, says to reload the page", async () => {
    archive.mockRejectedValue(REFUSAL);
    const { dialog } = setup(SVC, false);
    await confirm(dialog);
    expect(within(dialog).getByRole("alert").textContent).toBe(
      `${NOT_IN_GROUP} ${NOT_REFRESHED}`,
    );
  });

  it("on an unknown outcome, after a successful reload, says the list was refreshed", async () => {
    archive.mockRejectedValue(UNKNOWN_504);
    const { dialog, onSettled } = setup(SVC, true);
    await confirm(dialog);
    expect(within(dialog).getByRole("alert").textContent).toBe(
      `${UNKNOWN} ${REFRESHED}`,
    );
    expect(onSettled).toHaveBeenCalledTimes(1);
  });

  it("on an unknown outcome, after a FAILED reload, says to reload the page", async () => {
    archive.mockRejectedValue(UNKNOWN_504);
    const { dialog } = setup(SVC, false);
    await confirm(dialog);
    expect(within(dialog).getByRole("alert").textContent).toBe(
      `${UNKNOWN} ${NOT_REFRESHED}`,
    );
  });

  it("falls back to the approved sentence when the API sent none, and reloads", async () => {
    // The ruling covers the refusal and the 504; the fallback says "Nothing
    // was changed." and gets no line about the list.
    archive.mockRejectedValue({ status: 502, payload: null });
    const { dialog, onSettled } = setup();
    await confirm(dialog);
    expect(within(dialog).getByRole("alert").textContent).toBe(FALLBACK);
    expect(onSettled).toHaveBeenCalledTimes(1);
  });

  it("does not show the internal schema sentence as the API's message", async () => {
    archive.mockRejectedValue({
      status: 422,
      payload: {
        error: {
          code: 422,
          reason: "schema_uuid_parsing",
          message: "Request validation failed.",
        },
      },
    });
    const { dialog } = setup();
    await confirm(dialog);
    expect(within(dialog).getByRole("alert")).toHaveTextContent(FALLBACK);
  });

  it("forgets an earlier failure when opened for another service", async () => {
    archive.mockRejectedValue({ status: 502, payload: null });
    const { dialog, onClose, onSettled, rerender } = setup();
    await confirm(dialog);
    expect(within(dialog).getByRole("alert")).toBeInTheDocument();
    rerender(
      <ArchiveServiceDialog
        clientId="c1"
        service={{ ...SVC, service_id: "svc-1", title: "ZT" }}
        onClose={onClose}
        onSettled={onSettled}
      />,
    );
    expect(within(dialog).queryByRole("alert")).toBeNull();
  });
});
