import "@testing-library/jest-dom/vitest";

import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { beforeAll, describe, expect, it, vi } from "vitest";

import { DiscardDraftButton } from "./DiscardDraftButton";

// jsdom does not implement <dialog>.showModal()/.close(); the design-system
// Modal drives the native dialog imperatively (showModal on open, close on
// dismiss). Stub the two methods so the modal can open and the close event
// still fires, mirroring the browser.
beforeAll(() => {
  HTMLDialogElement.prototype.showModal = function showModal(): void {
    this.open = true;
  };
  HTMLDialogElement.prototype.close = function close(): void {
    this.open = false;
    this.dispatchEvent(new Event("close"));
  };
});

describe("DiscardDraftButton", () => {
  it("renders nothing unless the status is draft", () => {
    const { container } = render(
      <DiscardDraftButton
        status="approved"
        destructionSummary="3 capability items will be discarded."
        onConfirm={vi.fn()}
      />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("shows the trigger for a draft and opens the confirm modal on click", () => {
    const { container } = render(
      <DiscardDraftButton
        status="draft"
        destructionSummary="3 capability items will be discarded."
        onConfirm={vi.fn()}
      />,
    );
    const dialog = container.querySelector("dialog") as HTMLDialogElement;
    expect(dialog.open).toBe(false);

    fireEvent.click(screen.getByRole("button", { name: "Discard draft" }));

    expect(dialog.open).toBe(true);
    expect(
      within(dialog).getByText("3 capability items will be discarded."),
    ).toBeInTheDocument();
  });

  it("invokes onConfirm and closes when the modal is confirmed", async () => {
    const onConfirm = vi.fn().mockResolvedValue(undefined);
    const { container } = render(
      <DiscardDraftButton
        status="draft"
        destructionSummary="12 answers, including client-entered data, will be discarded."
        onConfirm={onConfirm}
      />,
    );
    const dialog = container.querySelector("dialog") as HTMLDialogElement;

    fireEvent.click(screen.getByRole("button", { name: "Discard draft" }));
    await act(async () => {
      fireEvent.click(
        within(dialog).getByRole("button", { name: "Yes, discard" }),
      );
    });

    expect(onConfirm).toHaveBeenCalledTimes(1);
    expect(dialog.open).toBe(false);
  });

  it("does not invoke onConfirm when the modal is cancelled", () => {
    const onConfirm = vi.fn();
    const { container } = render(
      <DiscardDraftButton
        status="draft"
        destructionSummary="3 scored techniques will be discarded."
        onConfirm={onConfirm}
      />,
    );
    const dialog = container.querySelector("dialog") as HTMLDialogElement;

    fireEvent.click(screen.getByRole("button", { name: "Discard draft" }));
    fireEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));

    expect(onConfirm).not.toHaveBeenCalled();
    expect(dialog.open).toBe(false);
  });
});
