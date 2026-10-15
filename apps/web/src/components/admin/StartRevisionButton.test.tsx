import "@testing-library/jest-dom/vitest";

import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { beforeAll, describe, expect, it, vi } from "vitest";

import { StartRevisionButton } from "./StartRevisionButton";

// jsdom has no <dialog>.showModal()/.close(); the design-system Modal drives
// the native dialog, so stub both, as DiscardDraftButton.test.tsx does.
beforeAll(() => {
  HTMLDialogElement.prototype.showModal = function showModal(): void {
    this.open = true;
  };
  HTMLDialogElement.prototype.close = function close(): void {
    this.open = false;
    this.dispatchEvent(new Event("close"));
  };
});

// The approved copy (#736 6136101129), written out, never imported.
const V2A =
  "This creates version 4 as a draft, with every answer, score, note and consultant edit copied from version 3. Version 3 and its reports are not changed, and the client sees nothing new until a report from version 4 is released.";

function openDialog(status = "approved", onStart = vi.fn()) {
  const view = render(
    <StartRevisionButton status={status} version={3} onStart={onStart} />,
  );
  fireEvent.click(screen.getByRole("button", { name: "Start a revision" }));
  const dialog = view.container.querySelector("dialog") as HTMLDialogElement;
  return { dialog, onStart };
}

describe("StartRevisionButton (#1120)", () => {
  it.each(["draft", "submitted", "discarded"])(
    "renders nothing for a %s record",
    (status) => {
      const { container } = render(
        <StartRevisionButton status={status} version={1} onStart={vi.fn()} />,
      );
      expect(container).toBeEmptyDOMElement();
    },
  );

  it.each(["approved", "released"])(
    "opens the approved dialog for a %s record",
    (status) => {
      const { dialog } = openDialog(status);
      expect(dialog.open).toBe(true);
      expect(
        within(dialog).getByText("Start a revision of version 3?"),
      ).toBeInTheDocument();
      expect(within(dialog).getByText(V2A)).toBeInTheDocument();
      expect(
        within(dialog).getByLabelText("What is this revision for?"),
      ).toBeInTheDocument();
      expect(
        within(dialog).getByText(
          "Required. Saved in the audit log with your name and the time.",
        ),
      ).toBeInTheDocument();
      expect(
        within(dialog).getByRole("button", { name: "Cancel" }),
      ).toBeInTheDocument();
    },
  );

  it("cannot start without a reason, and sends the trimmed reason", async () => {
    const { dialog, onStart } = openDialog(
      "approved",
      vi.fn().mockResolvedValue(undefined),
    );
    const start = within(dialog).getByRole("button", {
      name: "Start revision",
    });
    expect(start).toBeDisabled(); // positive control below
    fireEvent.change(
      within(dialog).getByLabelText("What is this revision for?"),
      {
        target: { value: "  Client found a typo  " },
      },
    );
    expect(start).toBeEnabled();
    await act(async () => {
      fireEvent.click(start);
    });
    expect(onStart).toHaveBeenCalledWith("Client found a typo");
    expect(dialog.open).toBe(false);
  });

  it("keeps the dialog open and shows the API's refusal", async () => {
    const refusal =
      "Version 4 is open as a draft. Approve it, or discard it, before starting another revision.";
    const { dialog } = openDialog(
      "released",
      vi.fn().mockRejectedValue(new Error(refusal)),
    );
    fireEvent.change(
      within(dialog).getByLabelText("What is this revision for?"),
      {
        target: { value: "Again" },
      },
    );
    await act(async () => {
      fireEvent.click(
        within(dialog).getByRole("button", { name: "Start revision" }),
      );
    });
    expect(dialog.open).toBe(true);
    expect(within(dialog).getByRole("alert")).toHaveTextContent(refusal);
  });

  it("caps the reason at the API's 2000 characters", () => {
    const { dialog } = openDialog();
    expect(
      within(dialog).getByLabelText("What is this revision for?"),
    ).toHaveAttribute("maxlength", "2000");
  });

  it("keeps an open dialog and its refusal when the record beneath becomes a draft", async () => {
    const refusal =
      "Version 4 is open as a draft. Approve it, or discard it, before starting another revision.";
    const onStart = vi.fn().mockRejectedValue(new Error(refusal));
    const view = render(
      <StartRevisionButton status="approved" version={3} onStart={onStart} />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Start a revision" }));
    const dialog = view.container.querySelector("dialog") as HTMLDialogElement;
    fireEvent.change(
      within(dialog).getByLabelText("What is this revision for?"),
      { target: { value: "Again" } },
    );
    await act(async () => {
      fireEvent.click(
        within(dialog).getByRole("button", { name: "Start revision" }),
      );
    });
    // The workspace re-reads the service and now shows its draft.
    view.rerender(
      <StartRevisionButton status="draft" version={4} onStart={onStart} />,
    );
    const still = view.container.querySelector("dialog") as HTMLDialogElement;
    expect(still.open).toBe(true);
    expect(within(still).getByRole("alert")).toHaveTextContent(refusal);
    // It still names the version it was opened on, as its refusal does.
    expect(
      within(still).getByText("Start a revision of version 3?"),
    ).toBeInTheDocument();
    expect(within(still).getByText(V2A)).toBeInTheDocument();
    // The trigger is gone, and the dialog can only be closed now.
    expect(
      screen.queryByRole("button", { name: "Start a revision" }),
    ).not.toBeInTheDocument();
    expect(
      within(still).getByRole("button", { name: "Start revision" }),
    ).toBeDisabled();
  });

  it("opens clean after a refusal, cancel and reopen", async () => {
    const refusal =
      "Version 4 is open as a draft. Approve it, or discard it, before starting another revision.";
    const { dialog } = openDialog(
      "approved",
      vi.fn().mockRejectedValue(new Error(refusal)),
    );
    fireEvent.change(
      within(dialog).getByLabelText("What is this revision for?"),
      { target: { value: "Again" } },
    );
    await act(async () => {
      fireEvent.click(
        within(dialog).getByRole("button", { name: "Start revision" }),
      );
    });
    expect(within(dialog).getByRole("alert")).toHaveTextContent(refusal);
    fireEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(dialog.open).toBe(false);

    fireEvent.click(screen.getByRole("button", { name: "Start a revision" }));
    expect(dialog.open).toBe(true);
    expect(within(dialog).queryByRole("alert")).not.toBeInTheDocument();
    expect(
      within(dialog).getByLabelText("What is this revision for?"),
    ).toHaveValue("");
    expect(
      within(dialog).getByRole("button", { name: "Start revision" }),
    ).toBeDisabled();
  });

  it("names the current version when reopened after the record moved on", () => {
    // Unkeyed in the workspace, so one button outlives v3 approved, v4 as a
    // draft, then v4 approved.
    const onStart = vi.fn();
    const view = render(
      <StartRevisionButton status="approved" version={3} onStart={onStart} />,
    );
    view.rerender(
      <StartRevisionButton status="approved" version={4} onStart={onStart} />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Start a revision" }));
    const dialog = view.container.querySelector("dialog") as HTMLDialogElement;
    expect(dialog.open).toBe(true);
    expect(
      within(dialog).getByText("Start a revision of version 4?"),
    ).toBeInTheDocument();
    expect(
      within(dialog).getByText(
        "This creates version 5 as a draft, with every answer, score, note and consultant edit copied from version 4. Version 4 and its reports are not changed, and the client sees nothing new until a report from version 5 is released.",
      ),
    ).toBeInTheDocument();
  });
});
