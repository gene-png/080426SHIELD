import "@testing-library/jest-dom/vitest";

import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import * as adminClient from "@/lib/admin/client";

import { ArchiveServiceButton } from "./ArchiveServiceButton";

/**
 * #896: one archive button per duplicate service on the Risk Register's
 * duplicate banner, with a confirm dialog in the `DiscardDraftButton` pattern.
 *
 * Every string is copied from the advisor's approval (#736 6042801745, on the
 * plan in 6042306149), never from the component: a test reading the
 * component's own constants agrees with it by construction.
 */

vi.mock("@/lib/admin/client", () => ({ archiveService: vi.fn() }));

const archiveService = vi.mocked(adminClient.archiveService);

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

function setup(onArchived = vi.fn()) {
  const { container } = render(
    <ArchiveServiceButton
      serviceId="svc-2"
      title="ZT 2"
      onArchived={onArchived}
    />,
  );
  const dialog = container.querySelector("dialog") as HTMLDialogElement;
  return { dialog, onArchived };
}

function open(dialog: HTMLDialogElement): void {
  fireEvent.click(screen.getByRole("button", { name: "Archive ZT 2" }));
  expect(dialog.open).toBe(true);
}

async function confirm(dialog: HTMLDialogElement): Promise<void> {
  await act(async () => {
    fireEvent.click(
      within(dialog).getByRole("button", { name: "Yes, archive" }),
    );
  });
}

describe("ArchiveServiceButton (#896)", () => {
  beforeEach(() => {
    archiveService.mockReset();
  });

  it("opens a confirm dialog naming the service, with the approved body", () => {
    const { dialog } = setup();
    expect(dialog.open).toBe(false);
    open(dialog);
    expect(
      within(dialog).getByRole("heading", { name: "Archive ZT 2?" }),
    ).toBeInTheDocument();
    expect(within(dialog).getByText(BODY)).toBeInTheDocument();
    expect(archiveService).not.toHaveBeenCalled();
  });

  it("archives nothing when cancelled", () => {
    const { dialog, onArchived } = setup();
    open(dialog);
    fireEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(dialog.open).toBe(false);
    expect(archiveService).not.toHaveBeenCalled();
    expect(onArchived).not.toHaveBeenCalled();
  });

  it("archives that service on confirm, closes, and reports it", async () => {
    archiveService.mockResolvedValue(undefined);
    const { dialog, onArchived } = setup();
    open(dialog);
    await confirm(dialog);
    expect(archiveService).toHaveBeenCalledWith("svc-2");
    expect(onArchived).toHaveBeenCalledTimes(1);
    expect(dialog.open).toBe(false);
  });

  it("says Archiving… while the archive is in flight", async () => {
    archiveService.mockReturnValue(new Promise(() => {}));
    const { dialog } = setup();
    open(dialog);
    await confirm(dialog);
    expect(
      within(dialog).getByRole("button", { name: "Archiving…" }),
    ).toBeDisabled();
    expect(
      within(dialog).getByRole("button", { name: "Cancel" }),
    ).toBeDisabled();
  });

  it("shows the API's typed message on failure and stays open", async () => {
    archiveService.mockRejectedValue({
      status: 504,
      payload: {
        error: {
          code: 504,
          reason: "upstream_outcome_unknown",
          message:
            "We couldn't confirm whether this finished. It may still complete; check before trying again.",
        },
      },
    });
    const { dialog, onArchived } = setup();
    open(dialog);
    await confirm(dialog);
    expect(within(dialog).getByRole("alert")).toHaveTextContent(
      "We couldn't confirm whether this finished. It may still complete; check before trying again.",
    );
    expect(within(dialog).getByRole("alert")).not.toHaveTextContent(FALLBACK);
    expect(dialog.open).toBe(true);
    expect(onArchived).not.toHaveBeenCalled();
  });

  it("falls back to the approved sentence when the API sent none", async () => {
    archiveService.mockRejectedValue({ status: 502, payload: null });
    const { dialog, onArchived } = setup();
    open(dialog);
    await confirm(dialog);
    expect(within(dialog).getByRole("alert")).toHaveTextContent(FALLBACK);
    expect(onArchived).not.toHaveBeenCalled();
  });

  it("does not show the internal schema sentence as the API's message", async () => {
    archiveService.mockRejectedValue({
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
    open(dialog);
    await confirm(dialog);
    expect(within(dialog).getByRole("alert")).toHaveTextContent(FALLBACK);
  });
});
