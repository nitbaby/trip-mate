import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { useParams } from "react-router-dom";
import { api, type ItemInput } from "../api/client";
import { Sheet } from "../components/Sheet";
import { Button, ErrorNote, Spinner, field, label } from "../components/ui";
import { focusDay, formatDay, formatTime, fromInputValue, groupByDay, splitLocal, toInputValue, todayIn } from "../lib/time";
import { useTrip } from "../lib/useTrip";
import type { ItemType, ItineraryItem } from "../types";

const ICON: Record<ItemType, string> = { flight: "✈️", hotel: "🏨", reservation: "🍽️", activity: "🎟️", transit: "🚆", note: "📝" };
const TYPES: ItemType[] = ["flight", "hotel", "reservation", "activity", "transit", "note"];

function ItemSheet({ tripId, item, defaultDate, onClose }: { tripId: string; item?: ItineraryItem; defaultDate: string; onClose: () => void }) {
  const qc = useQueryClient();
  const [f, setF] = useState({
    type: (item?.type ?? "activity") as ItemType, title: item?.title ?? "",
    start: toInputValue(item?.start_at ?? `${defaultDate}T09:00:00`), end: toInputValue(item?.end_at ?? null),
    location: item?.location ?? "", notes: item?.notes ?? "",
  });
  const [confirmDelete, setConfirmDelete] = useState(false);
  const done = () => { qc.invalidateQueries({ queryKey: ["itinerary", tripId] }); onClose(); };
  const body = (): ItemInput => ({
    type: f.type, title: f.title.trim(), start_at: fromInputValue(f.start)!, end_at: fromInputValue(f.end),
    location: f.location.trim() || null, notes: f.notes.trim() || null,
  });
  const save = useMutation({ mutationFn: () => (item ? api.updateItem(tripId, item.id, body()) : api.createItem(tripId, body())), onSuccess: done });
  const del = useMutation({ mutationFn: () => api.deleteItem(tripId, item!.id), onSuccess: done });
  const badRange = !!f.end && f.end < f.start;
  const submit = (e: FormEvent) => { e.preventDefault(); if (!badRange) save.mutate(); };
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value });

  return (
    <Sheet title={item ? "Edit item" : "Add to itinerary"} onClose={onClose}>
      <form onSubmit={submit} className="space-y-3">
        <div><label className={label} htmlFor="i-type">Type</label>
          <select id="i-type" className={field} value={f.type} onChange={set("type")}>
            {TYPES.map((t) => <option key={t} value={t}>{ICON[t]} {t[0].toUpperCase() + t.slice(1)}</option>)}
          </select></div>
        <div><label className={label} htmlFor="i-title">Title</label>
          <input id="i-title" required className={field} value={f.title} onChange={set("title")} /></div>
        <div className="grid grid-cols-2 gap-3">
          <div><label className={label} htmlFor="i-start">Starts</label>
            <input id="i-start" required type="datetime-local" className={field} value={f.start} onChange={set("start")} /></div>
          <div><label className={label} htmlFor="i-end">Ends (optional)</label>
            <input id="i-end" type="datetime-local" className={field} value={f.end} onChange={set("end")} /></div>
        </div>
        {badRange && <p role="alert" className="text-sm text-red-600">End time must be after the start.</p>}
        <div><label className={label} htmlFor="i-loc">Location</label>
          <input id="i-loc" className={field} value={f.location} onChange={set("location")} /></div>
        <div><label className={label} htmlFor="i-notes">Notes</label>
          <textarea id="i-notes" rows={2} className={`${field} py-2`} value={f.notes} onChange={set("notes")} /></div>
        <ErrorNote error={save.error ?? del.error} />
        <div className="flex gap-2">
          {item && (confirmDelete
            ? <Button variant="danger" onClick={() => del.mutate()} disabled={del.isPending}>Confirm delete</Button>
            : <Button variant="ghost" onClick={() => setConfirmDelete(true)}>Delete</Button>)}
          <button type="submit" disabled={save.isPending || badRange} className="min-h-11 flex-1 rounded-lg bg-indigo-600 px-4 font-medium text-white disabled:bg-indigo-300">
            {save.isPending ? "Saving…" : "Save"}
          </button>
        </div>
      </form>
    </Sheet>
  );
}

export default function ItineraryPage() {
  const { tripId = "" } = useParams();
  const trip = useTrip();
  const items = useQuery({ queryKey: ["itinerary", tripId], queryFn: () => api.itinerary(tripId) });
  const [sheet, setSheet] = useState<{ item?: ItineraryItem } | null>(null);
  const scrolled = useRef(false);

  const today = trip ? todayIn(trip.timezone) : "";
  const days = groupByDay(items.data ?? []);
  const focus = focusDay(days.map((d) => d.date), today);
  const titleOf = (id: string) => items.data?.find((i) => i.id === id)?.title ?? "another item";

  // ITIN-01: open on today (or the next day that has plans), once
  useEffect(() => {
    if (!scrolled.current && focus && items.data) {
      document.getElementById(`day-${focus}`)?.scrollIntoView({ block: "start" });
      scrolled.current = true;
    }
  }, [focus, items.data]);

  return (
    <main className="relative flex-1 overflow-y-auto p-4 pb-24">
      <h2 className="mb-3 text-lg font-semibold">Itinerary</h2>
      {items.isLoading && <Spinner label="Loading itinerary" />}
      <ErrorNote error={items.error} />
      {items.data?.length === 0 && <p className="py-8 text-center text-slate-500">Nothing planned yet. Add something, or ask TripMate in Chat.</p>}
      {days.map((d) => (
        <section key={d.date} id={`day-${d.date}`} aria-label={formatDay(d.date)} className="mb-5 scroll-mt-2">
          <h3 className="sticky top-0 mb-2 bg-slate-50 py-1 text-sm font-semibold text-slate-600 dark:bg-slate-950 dark:text-slate-300">
            {formatDay(d.date)}{d.date === today && <span className="ml-2 rounded-full bg-indigo-600 px-2 py-0.5 text-xs text-white">Today</span>}
          </h3>
          <ul className="space-y-2">
            {d.items.map((it) => (
              <li key={it.id}>
                <button type="button" onClick={() => setSheet({ item: it })}
                  className="flex min-h-14 w-full gap-3 rounded-xl border border-slate-200 bg-white p-3 text-left dark:border-slate-800 dark:bg-slate-900">
                  <span aria-hidden="true" className="text-2xl">{ICON[it.type]}</span>
                  <span className="min-w-0 flex-1">
                    <span className="block text-xs text-slate-500">
                      {formatTime(splitLocal(it.start_at).time)}{it.end_at && ` – ${formatTime(splitLocal(it.end_at).time)}`}
                    </span>
                    <span className="block font-medium">{it.title}</span>
                    {it.location && <span className="block truncate text-sm text-slate-500">{it.location}</span>}
                    {it.source === "agent" && <span className="mt-1 inline-block rounded-full bg-violet-100 px-2 py-0.5 text-xs font-medium text-violet-700 dark:bg-violet-900 dark:text-violet-200">Added by TripMate</span>}
                    {!!it.conflicts_with?.length && (
                      <span role="note" className="mt-1 block text-sm font-medium text-amber-700 dark:text-amber-300">
                        ⚠ Overlaps with {it.conflicts_with.map(titleOf).join(", ")}
                      </span>
                    )}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </section>
      ))}
      <button type="button" onClick={() => setSheet({})} aria-label="Add itinerary item"
        className="fixed bottom-20 right-[max(1rem,calc(50%-14rem+1rem))] z-30 flex size-14 items-center justify-center rounded-full bg-indigo-600 text-3xl text-white shadow-lg">+</button>
      {sheet && <ItemSheet tripId={tripId} item={sheet.item} defaultDate={focus ?? trip?.start_date ?? today} onClose={() => setSheet(null)} />}
    </main>
  );
}
