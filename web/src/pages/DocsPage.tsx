import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { api } from "../api/client";
import { Button, ErrorNote, Spinner } from "../components/ui";
import { useTrip } from "../lib/useTrip";
import type { DocStatus, KeyFact, TripDoc } from "../types";

const STATUS: Record<DocStatus, { text: string; cls: string }> = {
  queued: { text: "Queued", cls: "bg-slate-200 text-slate-700 dark:bg-slate-700 dark:text-slate-200" },
  processing: { text: "Reading…", cls: "bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-100" },
  ready: { text: "Ready", cls: "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-100" },
  failed: { text: "Failed", cls: "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-100" },
};
const TYPE_LABEL: Record<string, string> = { confirmation: "Confirmation", itinerary: "Itinerary", rules: "Rules", guide: "Guide" };

/** DOC-05/06: sensitive values are masked; Reveal fetches the raw value and re-masks after 30 s. */
export function FactCard({ docId, fact }: { docId: string; fact: KeyFact }) {
  const [revealed, setRevealed] = useState<{ value: string; left: number } | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setInterval>>(undefined);
  useEffect(() => () => clearInterval(timer.current), []);

  const hide = () => { clearInterval(timer.current); setRevealed(null); };
  const reveal = async () => {
    try {
      const r = await api.reveal(docId, fact.index);
      setErr(null);
      setRevealed({ value: r.value, left: r.reveal_seconds });
      clearInterval(timer.current);
      timer.current = setInterval(() => setRevealed((cur) => {
        if (!cur || cur.left <= 1) { clearInterval(timer.current); return null; }
        return { ...cur, left: cur.left - 1 };
      }), 1000);
    } catch (e) { setErr((e as Error).message); }
  };

  return (
    <div className="rounded-lg bg-slate-100 p-2 dark:bg-slate-800">
      <dt className="text-xs text-slate-500">{fact.label}</dt>
      <dd className="flex items-center justify-between gap-2 text-sm font-medium">
        <span className={fact.sensitive ? "break-all font-mono" : "break-words"} data-testid="fact-value">{revealed ? revealed.value : fact.value}</span>
        {fact.sensitive && (
          <button type="button" onClick={revealed ? hide : reveal} aria-label={`${revealed ? "Hide" : "Reveal"} ${fact.label}`}
            className="min-h-11 shrink-0 rounded-md px-2 text-xs font-semibold text-indigo-600 dark:text-indigo-300">
            {revealed ? `Hide (${revealed.left}s)` : "Reveal"}
          </button>
        )}
      </dd>
      {err && <p role="alert" className="text-xs text-red-600">{err}</p>}
    </div>
  );
}

function DocCard({ tripId, doc }: { tripId: string; doc: TripDoc }) {
  const qc = useQueryClient();
  const [confirming, setConfirming] = useState(false);
  const del = useMutation({ mutationFn: () => api.deleteDoc(tripId, doc.id), onSuccess: () => qc.invalidateQueries({ queryKey: ["trip", tripId] }) });
  const st = STATUS[doc.status];
  return (
    <li className="rounded-xl border border-slate-200 bg-white p-3 dark:border-slate-800 dark:bg-slate-900">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="truncate font-medium">{doc.filename}</p>
          <p className="text-xs text-slate-500">{doc.doc_type ? TYPE_LABEL[doc.doc_type] ?? doc.doc_type : "Type pending"}</p>
        </div>
        <span className={`shrink-0 rounded-full px-2 py-0.5 text-xs font-semibold ${st.cls}`}>{st.text}</span>
      </div>
      {doc.status === "failed" && <p role="alert" className="mt-2 text-sm text-red-600">{doc.error ?? "Could not read this file."} Delete it and upload again.</p>}
      {doc.status === "ready" && doc.key_facts.length > 0 && (
        <dl className="mt-3 grid grid-cols-1 gap-2">
          {doc.key_facts.map((f) => <FactCard key={f.index} docId={doc.id} fact={f} />)}
        </dl>
      )}
      <div className="mt-2 flex justify-end">
        {confirming ? (
          <div className="flex gap-2">
            <Button variant="ghost" onClick={() => setConfirming(false)}>Keep</Button>
            <Button variant="danger" onClick={() => del.mutate()} disabled={del.isPending}>Delete {doc.filename}</Button>
          </div>
        ) : (
          <button type="button" onClick={() => setConfirming(true)} className="min-h-11 px-2 text-sm text-slate-500" aria-label={`Delete ${doc.filename}`}>Delete</button>
        )}
      </div>
    </li>
  );
}

export default function DocsPage() {
  const { tripId = "" } = useParams();
  const trip = useTrip();
  const qc = useQueryClient();
  const input = useRef<HTMLInputElement>(null);
  const upload = useMutation({
    mutationFn: async (files: File[]) => { for (const f of files) await api.upload(tripId, f); },
    onSettled: () => qc.invalidateQueries({ queryKey: ["trip", tripId] }),
  });

  return (
    <main className="flex-1 overflow-y-auto p-4">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-lg font-semibold">Documents</h2>
        <Button onClick={() => input.current?.click()} disabled={upload.isPending}>{upload.isPending ? "Uploading…" : "Upload"}</Button>
        <input ref={input} type="file" multiple hidden accept=".pdf,.txt,.md,application/pdf,text/plain,text/markdown" aria-label="Choose documents to upload"
          onChange={(e) => { const f = Array.from(e.target.files ?? []); if (f.length) upload.mutate(f); e.target.value = ""; }} />
      </div>
      <p className="mb-3 text-sm text-slate-500">Add booking confirmations, itineraries and local rules (PDF, TXT, MD). Passport, booking and card numbers stay masked until you tap Reveal.</p>
      <ErrorNote error={upload.error} />
      {!trip && <Spinner label="Loading documents" />}
      {trip && trip.documents.length === 0 && <p className="py-8 text-center text-slate-500">No documents yet.</p>}
      <ul className="space-y-3">{trip?.documents.map((d) => <DocCard key={d.id} tripId={tripId} doc={d} />)}</ul>
    </main>
  );
}
