import type { ToolCall } from "../types";

/** CHAT-04: tool calls appear as collapsed cards that can be expanded. */
export function ToolCard({ tool }: { tool: ToolCall }) {
  const icon = tool.status === "running" ? "⏳" : tool.status === "ok" ? "✓" : "⚠";
  return (
    <details className="group rounded-lg border border-slate-200 bg-slate-50 text-sm dark:border-slate-700 dark:bg-slate-800/60">
      <summary className="flex min-h-11 cursor-pointer list-none items-center gap-2 px-3">
        <span aria-hidden="true">{icon}</span>
        <span className="flex-1">{tool.label}{tool.status === "running" && "…"}</span>
        <span className="text-xs text-slate-500 group-open:rotate-90" aria-hidden="true">›</span>
      </summary>
      <div className="border-t border-slate-200 px-3 py-2 text-slate-600 dark:border-slate-700 dark:text-slate-300">
        <p><span className="font-mono text-xs">{tool.name}</span></p>
        <p>{tool.status === "running" ? "Working…" : tool.summary}</p>
      </div>
    </details>
  );
}
