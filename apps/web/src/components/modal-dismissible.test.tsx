import "@testing-library/jest-dom/vitest";

import { fireEvent, render } from "@testing-library/react";
import { beforeAll, describe, expect, it, vi } from "vitest";

import { Modal } from "@shield/design-system";

/**
 * #896 round 3, R3-1: the design-system Modal gains an OPT-IN `dismissible`
 * prop. Default (true) is every existing caller's behaviour, unchanged: Esc
 * and a backdrop click close it. `dismissible={false}` keeps it open through
 * both, and through a native close the browser forces anyway (a second Esc
 * can close a dialog whose `cancel` was prevented), so state cannot split
 * from what is on screen.
 *
 * The package has no test runner of its own; this suite runs it through the
 * web app's, as every other Modal test does.
 */

// jsdom does not implement <dialog>.showModal()/.close(); the same stubs as
// DiscardDraftButton.test.tsx.
beforeAll(() => {
  HTMLDialogElement.prototype.showModal = function showModal(): void {
    this.open = true;
  };
  HTMLDialogElement.prototype.close = function close(): void {
    this.open = false;
    this.dispatchEvent(new Event("close"));
  };
});

function setup(dismissible?: boolean) {
  const onClose = vi.fn();
  const { container } = render(
    <Modal open onClose={onClose} title="T" dismissible={dismissible}>
      body
    </Modal>,
  );
  const dialog = container.querySelector("dialog") as HTMLDialogElement;
  return { dialog, onClose };
}

function escape(dialog: HTMLDialogElement): Event {
  const cancel = new Event("cancel", { cancelable: true });
  dialog.dispatchEvent(cancel);
  return cancel;
}

describe("Modal dismissible (#896 R3-1)", () => {
  it("by default, a backdrop click closes it and reports the close", () => {
    const { dialog, onClose } = setup();
    expect(dialog.open).toBe(true);
    fireEvent.click(dialog);
    expect(dialog.open).toBe(false);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("by default, Esc's cancel is not prevented", () => {
    const { dialog } = setup();
    expect(escape(dialog).defaultPrevented).toBe(false);
  });

  it("when not dismissible, a backdrop click leaves it open", () => {
    const { dialog, onClose } = setup(false);
    // Not even closed and re-opened: a real browser would flicker the
    // backdrop and move focus, so the click must not reach `close()` at all.
    const close = vi.spyOn(dialog, "close");
    fireEvent.click(dialog);
    expect(close).not.toHaveBeenCalled();
    expect(dialog.open).toBe(true);
    expect(onClose).not.toHaveBeenCalled();
  });

  it("when not dismissible, Esc's cancel is prevented", () => {
    const { dialog } = setup(false);
    expect(escape(dialog).defaultPrevented).toBe(true);
  });

  it("when not dismissible, a close the browser forces anyway re-opens it", () => {
    const { dialog, onClose } = setup(false);
    dialog.close();
    expect(dialog.open).toBe(true);
    expect(onClose).not.toHaveBeenCalled();
  });
});
