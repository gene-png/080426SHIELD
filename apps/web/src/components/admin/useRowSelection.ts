"use client";
import * as React from "react";

export interface RowSelection {
  /** Selected ids, in the order `ids` lists them. */
  selected: string[];
  isSelected: (id: string) => boolean;
  toggle: (id: string) => void;
  /** Select every id, or clear them all when every id is already selected. */
  toggleAll: () => void;
  clear: () => void;
  allSelected: boolean;
}

/**
 * Checkbox selection over a list of row ids (#641), kept generic so ATT&CK
 * gap triage (#557) can reuse it.
 *
 * The selection is DERIVED against the current ids rather than reset when they
 * change: a row that leaves the list (a reload, a discard) leaves the
 * selection in the same render, so a bulk action can never name a row that is
 * no longer shown.
 */
export function useRowSelection(ids: readonly string[]): RowSelection {
  const [chosen, setChosen] = React.useState<ReadonlySet<string>>(new Set());
  const selected = React.useMemo(
    () => ids.filter((id) => chosen.has(id)),
    [ids, chosen],
  );
  const allSelected = ids.length > 0 && selected.length === ids.length;

  const toggle = React.useCallback((id: string) => {
    setChosen((curr) => {
      const next = new Set(curr);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const toggleAll = React.useCallback(() => {
    setChosen(allSelected ? new Set() : new Set(ids));
  }, [allSelected, ids]);

  const clear = React.useCallback(() => setChosen(new Set()), []);

  const isSelected = React.useCallback(
    (id: string) => selected.includes(id),
    [selected],
  );

  return { selected, isSelected, toggle, toggleAll, clear, allSelected };
}
