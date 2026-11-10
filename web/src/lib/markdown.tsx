import type { ReactNode } from "react";
import type { Citation } from "../types";

type Cite = (c: Citation) => void;

/** Inline: **bold**, *italic*, and [n] citation markers. Everything is rendered as React text (no HTML injection). */
function inline(text: string, citations: Record<string, Citation>, onCite: Cite, key: string): ReactNode[] {
  const parts = text.split(/(\*\*[^*]+\*\*|\[\d+\]|\*[^*\s][^*]*\*)/g);
  return parts.filter(Boolean).map((p, i) => {
    const k = `${key}-${i}`;
    if (p.startsWith("**") && p.endsWith("**") && p.length > 4) return <strong key={k}>{p.slice(2, -2)}</strong>;
    if (/^\[\d+\]$/.test(p)) {
      const c = citations[p];
      if (!c) return null; // unknown marker: hide rather than show a dead reference
      return (
        <button key={k} type="button" onClick={() => onCite(c)} aria-label={`Source ${p.slice(1, -1)}: ${c.label}`}
          className="mx-0.5 inline-flex min-h-6 min-w-6 items-center justify-center rounded-full bg-indigo-100 px-1.5 align-baseline text-xs font-semibold text-indigo-700 dark:bg-indigo-900 dark:text-indigo-200">
          {p.slice(1, -1)}
        </button>
      );
    }
    if (p.startsWith("*") && p.endsWith("*") && p.length > 2) return <em key={k}>{p.slice(1, -1)}</em>;
    return p;
  });
}

export function Markdown({ text, citations, onCite }: { text: string; citations: Record<string, Citation>; onCite: Cite }) {
  const lines = text.split("\n");
  const blocks: ReactNode[] = [];
  let list: string[] = [];
  const flush = (i: number) => {
    if (!list.length) return;
    blocks.push(
      <ul key={`ul${i}`} className="my-1 list-disc space-y-1 pl-5">
        {list.map((l, j) => <li key={j}>{inline(l, citations, onCite, `li${i}-${j}`)}</li>)}
      </ul>,
    );
    list = [];
  };
  lines.forEach((line, i) => {
    const m = line.match(/^\s*(?:[*-]|\d+\.)\s+(.*)$/);
    if (m) { list.push(m[1]); return; }
    flush(i);
    if (line.trim()) blocks.push(<p key={`p${i}`} className="my-1">{inline(line, citations, onCite, `p${i}`)}</p>);
  });
  flush(lines.length);
  return <>{blocks}</>;
}
