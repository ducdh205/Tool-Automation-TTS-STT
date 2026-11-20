import type { OpKind, WordOp } from "./api";

export function formatPct(x: number | null | undefined): string {
  if (x === null || x === undefined || Number.isNaN(x)) return "—";
  const v = Math.round(x * 1000) / 10;
  return `${Number.isInteger(v) ? v : v.toFixed(1).replace(".", ",")}%`;
}

export interface Segment { text: string; kind: OpKind; title?: string }

/** Words as the STT heard them, with missing words (del) shown struck through. */
export function renderOps(ops: WordOp[]): Segment[] {
  return ops.map((o) => {
    switch (o.op) {
      case "sub": return { text: o.hyp ?? "", kind: "sub", title: `đúng: ${o.ref}` };
      case "del": return { text: o.ref ?? "", kind: "del", title: "thiếu từ" };
      case "ins": return { text: o.hyp ?? "", kind: "ins", title: "thừa từ" };
      default: return { text: o.hyp ?? "", kind: "equal" };
    }
  });
}
