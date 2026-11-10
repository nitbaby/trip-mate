import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { useParams } from "react-router-dom";
import { SourceDrawer } from "../components/SourceDrawer";
import { ToolCard } from "../components/ToolCard";
import { Button } from "../components/ui";
import { needsBanner } from "../lib/chatReducer";
import { Markdown } from "../lib/markdown";
import { useChat } from "../lib/useChat";
import { useTrip } from "../lib/useTrip";
import type { AssistantMessage, Citation, TripDetail } from "../types";

/** CHAT-07: suggestions drawn from the documents the trip actually has. */
function suggestions(trip?: TripDetail): string[] {
  const types = new Set(trip?.documents.filter((d) => d.status === "ready").map((d) => d.doc_type));
  const out: string[] = [];
  if (types.has("confirmation")) out.push("What time is check-out, and does the hotel include breakfast?");
  if (types.has("itinerary")) out.push("Is my 6 PM flight delayed?");
  if (types.has("rules")) out.push("What's the rule for bringing medication into Japan?");
  out.push("Find a vegetarian place near my hotel that's open now.", "Add a dinner reservation at 8 PM to tomorrow's itinerary.");
  return out.slice(0, 4);
}

function Assistant({ m, onCite, onRetry, last }: { m: AssistantMessage; onCite: (c: Citation) => void; onRetry: () => void; last: boolean }) {
  const streaming = m.status === "streaming";
  return (
    <div className="max-w-[92%] space-y-2 self-start">
      {m.tools.map((t) => <ToolCard key={t.id} tool={t} />)}
      {(m.text || streaming) && (
        <div className="rounded-2xl rounded-tl-sm border border-slate-200 bg-white px-4 py-2 dark:border-slate-800 dark:bg-slate-900">
          <Markdown text={m.text} citations={m.citations} onCite={onCite} />
          {streaming && <span className="tm-cursor" aria-hidden="true">▍</span>}
          {streaming && !m.text && <span className="text-sm text-slate-500">Thinking…</span>}
        </div>
      )}
      {m.itinerary.length > 0 && <p className="text-sm text-violet-700 dark:text-violet-300">✓ Itinerary updated by TripMate</p>}
      {needsBanner(m) && m.status === "done" && (
        <p role="note" className="rounded-lg bg-amber-50 p-3 text-sm text-amber-900 dark:bg-amber-950 dark:text-amber-100">
          {m.confidence === "none" ? "Not found in your documents." : "Low confidence: this may not be fully supported by your documents."} Check an official source to be sure.
        </p>
      )}
      {m.verify && (
        <p role="note" className="rounded-lg bg-sky-50 p-3 text-sm text-sky-900 dark:bg-sky-950 dark:text-sky-100"><strong>Verify:</strong> {m.verify}</p>
      )}
      {m.status === "error" && m.error && (
        <div role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-800 dark:bg-red-950 dark:text-red-100">
          {m.error.message}
          {m.error.retryable && last && <Button variant="ghost" className="ml-2" onClick={onRetry}>Retry</Button>}
        </div>
      )}
      {m.status === "stopped" && (
        <p className="text-sm text-slate-500">Stopped. {last && <button type="button" onClick={onRetry} className="min-h-11 font-semibold text-indigo-600 dark:text-indigo-300">Retry</button>}</p>
      )}
    </div>
  );
}

export default function ChatPage() {
  const { tripId = "" } = useParams();
  const trip = useTrip();
  const { messages, busy, send, stop, retry, reset, announce } = useChat(tripId);
  const [draft, setDraft] = useState("");
  const [source, setSource] = useState<Citation | null>(null);
  const bottom = useRef<HTMLDivElement>(null);
  const stick = useRef(true);

  useEffect(() => { if (stick.current) bottom.current?.scrollIntoView({ block: "end" }); }, [messages]);

  const submit = (e?: FormEvent) => { e?.preventDefault(); if (draft.trim() && !busy) { void send(draft); setDraft(""); stick.current = true; } };
  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit(); } };
  const ask = (q: string) => { stick.current = true; void send(q); };

  const dest = trip?.destinations[0] ?? "my destination";
  const quick = [
    ["Today's plan", "What's on my itinerary today?"],
    ["Weather", `What's the weather forecast for ${dest} for the next 3 days?`],
    ["Flight status", "Is my next flight on time?"],
    ["Nearby food", "Find a vegetarian place near my hotel that's open now."],
  ] as const;

  return (
    <>
      <div className="flex items-center justify-end px-3 pt-1">
        <button type="button" onClick={reset} disabled={messages.length === 0} className="min-h-11 px-2 text-sm text-slate-600 disabled:opacity-40 dark:text-slate-300">New chat</button>
      </div>
      <div className="flex-1 overflow-y-auto px-3 pb-2" onScroll={(e) => {
        const el = e.currentTarget; stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
      }}>
        {messages.length === 0 ? (
          <div className="py-6">
            <p className="mb-1 text-lg font-semibold">Ask about your trip</p>
            <p className="mb-4 text-sm text-slate-500">Answers come from your documents, with sources you can tap.</p>
            <ul className="space-y-2" aria-label="Suggested questions">
              {suggestions(trip).map((s) => (
                <li key={s}><button type="button" onClick={() => ask(s)} disabled={busy}
                  className="min-h-11 w-full rounded-xl border border-indigo-200 bg-white px-4 py-2 text-left text-sm dark:border-indigo-900 dark:bg-slate-900">{s}</button></li>
              ))}
            </ul>
          </div>
        ) : (
          <div className="flex flex-col gap-3 py-2">
            {messages.map((m, i) => m.role === "user"
              ? <p key={m.id} className="max-w-[85%] self-end rounded-2xl rounded-tr-sm bg-indigo-600 px-4 py-2 text-white">{m.text}</p>
              : <Assistant key={m.id} m={m} onCite={setSource} onRetry={retry} last={i === messages.length - 1} />)}
          </div>
        )}
        <div ref={bottom} />
      </div>
      {/* A11Y-03: announce each finished answer once, never token by token */}
      <div className="sr-only" aria-live="polite" aria-atomic="true">{announce}</div>

      <div className="border-t border-slate-200 bg-slate-50 dark:border-slate-800 dark:bg-slate-950">
        <div className="flex gap-2 overflow-x-auto px-3 py-2" role="group" aria-label="Quick actions">
          {quick.map(([label, q]) => (
            <button key={label} type="button" disabled={busy} onClick={() => ask(q)}
              className="min-h-11 shrink-0 rounded-full border border-slate-300 bg-white px-4 text-sm disabled:opacity-50 dark:border-slate-700 dark:bg-slate-900">{label}</button>
          ))}
        </div>
        <form onSubmit={submit} className="flex items-end gap-2 px-3 pb-2">
          <label htmlFor="composer" className="sr-only">Message</label>
          <textarea id="composer" rows={1} value={draft} onChange={(e) => setDraft(e.target.value)} onKeyDown={onKey}
            placeholder="Ask about your trip…" maxLength={4000}
            className="max-h-32 min-h-11 flex-1 resize-none rounded-2xl border border-slate-300 bg-white px-4 py-2.5 text-base dark:border-slate-700 dark:bg-slate-800" />
          {busy
            ? <Button variant="danger" onClick={stop} aria-label="Stop answering">Stop</Button>
            : <button type="submit" disabled={!draft.trim()} className="min-h-11 rounded-2xl bg-indigo-600 px-5 font-medium text-white disabled:bg-indigo-300">Send</button>}
        </form>
      </div>
      {source && <SourceDrawer citation={source} onClose={() => setSource(null)} />}
    </>
  );
}
