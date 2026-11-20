/** Rows picked in the table. Nothing selected means "all eligible" for every action. */
export interface Selection {
  ids: ReadonlySet<number>;
  /** Index (in the visible list) of the last plain click: the start of a shift-click range. */
  anchor: number | null;
}

export const emptySelection: Selection = { ids: new Set(), anchor: null };

export function clickRow(sel: Selection, visibleIds: number[], index: number, shift: boolean): Selection {
  const ids = new Set(sel.ids);
  if (shift && sel.anchor !== null && sel.anchor < visibleIds.length) {
    const [a, b] = sel.anchor < index ? [sel.anchor, index] : [index, sel.anchor];
    for (let i = a; i <= b; i++) ids.add(visibleIds[i]);
    return { ids, anchor: sel.anchor };
  }
  const id = visibleIds[index];
  if (ids.has(id)) ids.delete(id);
  else ids.add(id);
  return { ids, anchor: index };
}

export function toggleAllVisible(sel: Selection, visibleIds: number[]): Selection {
  const ids = new Set(sel.ids);
  const all = visibleIds.length > 0 && visibleIds.every((id) => ids.has(id));
  for (const id of visibleIds) {
    if (all) ids.delete(id);
    else ids.add(id);
  }
  return { ids, anchor: null };
}

export function prune(sel: Selection, allowed: ReadonlySet<number>): Selection {
  const ids = new Set([...sel.ids].filter((id) => allowed.has(id)));
  return ids.size === sel.ids.size ? sel : { ids, anchor: null };
}
