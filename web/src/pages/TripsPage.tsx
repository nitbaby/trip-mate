import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { Button, ErrorNote, Spinner, field, label } from "../components/ui";

const tz = Intl.DateTimeFormat().resolvedOptions().timeZone;

export default function TripsPage() {
  const nav = useNavigate();
  const qc = useQueryClient();
  const trips = useQuery({ queryKey: ["trips"], queryFn: api.trips });
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState({ name: "", destinations: "", start_date: "", end_date: "", timezone: tz });
  const create = useMutation({
    mutationFn: () => api.createTrip({ ...form, destinations: form.destinations.split(",").map((s) => s.trim()).filter(Boolean) }),
    onSuccess: (t) => { qc.invalidateQueries({ queryKey: ["trips"] }); nav(`/trips/${t.id}/docs`); },
  });
  const set = (k: keyof typeof form) => (e: { target: { value: string } }) => setForm({ ...form, [k]: e.target.value });
  const submit = (e: FormEvent) => { e.preventDefault(); create.mutate(); };

  return (
    <main className="flex-1 overflow-y-auto p-4 pb-[max(1rem,env(safe-area-inset-bottom))]">
      <h1 className="mb-1 text-2xl font-bold text-indigo-700 dark:text-indigo-300">TripMate</h1>
      <p className="mb-4 text-sm text-slate-500">Your trip, answered from your own documents.</p>

      {trips.isLoading && <Spinner label="Loading trips" />}
      <ErrorNote error={trips.error} />
      <ul className="space-y-2" aria-label="Your trips">
        {trips.data?.map((t) => (
          <li key={t.id}>
            <Link to={`/trips/${t.id}/chat`} className="block min-h-11 rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
              <span className="block font-semibold">{t.name}</span>
              <span className="text-sm text-slate-500">{t.destinations.join(", ")} · {t.start_date} → {t.end_date}</span>
            </Link>
          </li>
        ))}
      </ul>
      {trips.data?.length === 0 && <p className="py-6 text-center text-slate-500">No trips yet. Create your first one.</p>}

      {!creating ? (
        <Button className="mt-4 w-full" onClick={() => setCreating(true)}>New trip</Button>
      ) : (
        <form onSubmit={submit} className="mt-4 space-y-3 rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
          <h2 className="font-semibold">New trip</h2>
          <div><label className={label} htmlFor="t-name">Name</label>
            <input id="t-name" required className={field} value={form.name} onChange={set("name")} placeholder="Tokyo, Dec 2026" /></div>
          <div><label className={label} htmlFor="t-dest">Destinations (comma separated)</label>
            <input id="t-dest" required className={field} value={form.destinations} onChange={set("destinations")} placeholder="Tokyo, Kyoto" /></div>
          <div className="grid grid-cols-2 gap-3">
            <div><label className={label} htmlFor="t-start">Start</label>
              <input id="t-start" required type="date" className={field} value={form.start_date} onChange={set("start_date")} /></div>
            <div><label className={label} htmlFor="t-end">End</label>
              <input id="t-end" required type="date" min={form.start_date} className={field} value={form.end_date} onChange={set("end_date")} /></div>
          </div>
          <div><label className={label} htmlFor="t-tz">Timezone</label>
            <input id="t-tz" required className={field} value={form.timezone} onChange={set("timezone")} placeholder="Asia/Tokyo" /></div>
          <ErrorNote error={create.error} />
          <div className="flex gap-2">
            <Button variant="ghost" onClick={() => setCreating(false)}>Cancel</Button>
            <button type="submit" disabled={create.isPending} className="min-h-11 flex-1 rounded-lg bg-indigo-600 px-4 font-medium text-white disabled:bg-indigo-300">
              {create.isPending ? "Creating…" : "Create trip"}
            </button>
          </div>
        </form>
      )}
    </main>
  );
}
