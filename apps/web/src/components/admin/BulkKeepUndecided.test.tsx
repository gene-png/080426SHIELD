import "@testing-library/jest-dom/vitest";

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeAll, describe, expect, it, vi } from "vitest";

import { TechDebtProxyError } from "@/lib/tech_debt/client";
import type { CapabilityItem } from "@/lib/tech_debt/types";

import { BulkKeepUndecided } from "./BulkKeepUndecided";

// TD-11 (for #1055). Copy approved on #736 (6205607786, ruled 6206818759
// item 6), typed here, never imported from the component.

function row(
  id: string,
  disposition: string | null,
  parent: string | null = null,
): CapabilityItem {
  return {
    id,
    name: id,
    disposition,
    parent_item_id: parent,
  } as unknown as CapabilityItem;
}

const ITEMS = [
  row("a", null),
  row("b", "cut"),
  row("c", null),
  row("bundle", "keep"),
  row("part", null, "bundle"), // a part carries its own disposition
];

// jsdom has no <dialog>.showModal()/.close(); the design-system Modal opens one.
// The same stub as AttackWorkspace.run-supersede.test.tsx.
beforeAll(() => {
  HTMLDialogElement.prototype.showModal = function showModal(): void {
    this.open = true;
  };
  HTMLDialogElement.prototype.close = function close(): void {
    this.open = false;
    this.dispatchEvent(new Event("close"));
  };
});

describe("BulkKeepUndecided (TD-11)", () => {
  it("names the undecided count, parts included", () => {
    render(<BulkKeepUndecided items={ITEMS} editable onKeep={vi.fn()} />);
    expect(
      screen.getByRole("button", { name: /^Keep 3 undecided rows$/ }),
    ).toBeInTheDocument();
  });

  it("uses the singular for one row", () => {
    render(
      <BulkKeepUndecided
        items={[row("a", null), row("b", "cut")]}
        editable
        onKeep={vi.fn()}
      />,
    );
    expect(
      screen.getByRole("button", { name: /^Keep 1 undecided row$/ }),
    ).toBeInTheDocument();
  });

  it("asks first, then sends exactly the undecided rows", async () => {
    const onKeep = vi.fn(() => Promise.resolve());
    render(<BulkKeepUndecided items={ITEMS} editable onKeep={onKeep} />);
    fireEvent.click(
      screen.getByRole("button", { name: /^Keep 3 undecided rows$/ }),
    );
    expect(
      screen.getByText(
        "Set 3 undecided rows to Keep? Rows that already have a decision are not changed.",
      ),
    ).toBeInTheDocument();
    expect(onKeep).not.toHaveBeenCalled();
    // The modal's confirm is the second button of that name.
    const buttons = screen.getAllByRole("button", {
      name: /^Keep 3 undecided rows$/,
    });
    fireEvent.click(buttons[buttons.length - 1]);
    await waitFor(() => expect(onKeep).toHaveBeenCalledTimes(1));
    expect(onKeep).toHaveBeenCalledWith(["a", "c", "part"]);
    expect(await screen.findByText("Set 3 rows to Keep.")).toBeInTheDocument();
  });

  it("Cancel sends nothing", () => {
    const onKeep = vi.fn(() => Promise.resolve());
    render(<BulkKeepUndecided items={ITEMS} editable onKeep={onKeep} />);
    fireEvent.click(
      screen.getByRole("button", { name: /^Keep 3 undecided rows$/ }),
    );
    fireEvent.click(screen.getByRole("button", { name: /^Cancel$/ }));
    expect(onKeep).not.toHaveBeenCalled();
  });

  it("shows the API's refusal, never a success line", async () => {
    // The API's typed 409, as the proxy hands it on.
    const onKeep = vi.fn(() =>
      Promise.reject(
        new TechDebtProxyError(409, {
          error: {
            reason: "capability_items_already_decided",
            message: "1 of the 3 selected rows already have a decision.",
          },
        }),
      ),
    );
    render(<BulkKeepUndecided items={ITEMS} editable onKeep={onKeep} />);
    fireEvent.click(
      screen.getByRole("button", { name: /^Keep 3 undecided rows$/ }),
    );
    const buttons = screen.getAllByRole("button", {
      name: /^Keep 3 undecided rows$/,
    });
    fireEvent.click(buttons[buttons.length - 1]);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "1 of the 3 selected rows already have a decision.",
    );
    expect(screen.queryByText(/to Keep\.$/)).toBeNull();
  });

  it("is not shown when nothing is undecided, or on a released list", () => {
    // POSITIVE CONTROL first: the same rows on an editable list do render.
    const { unmount } = render(
      <BulkKeepUndecided items={ITEMS} editable onKeep={vi.fn()} />,
    );
    expect(
      screen.getByRole("button", { name: /undecided/ }),
    ).toBeInTheDocument();
    unmount();
    const { unmount: u2 } = render(
      <BulkKeepUndecided items={ITEMS} editable={false} onKeep={vi.fn()} />,
    );
    expect(screen.queryByRole("button", { name: /undecided/ })).toBeNull();
    u2();
    render(
      <BulkKeepUndecided items={[row("b", "cut")]} editable onKeep={vi.fn()} />,
    );
    expect(screen.queryByRole("button", { name: /undecided/ })).toBeNull();
  });
});
