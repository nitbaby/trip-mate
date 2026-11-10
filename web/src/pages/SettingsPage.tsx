import { useQuery } from "@tanstack/react-query";
import { useParams } from "react-router-dom";
import { api } from "../api/client";
import { ErrorNote, field, label } from "../components/ui";
import { setPrefs, usePrefs } from "../lib/prefs";

const NAMES: Record<string, string> = { flight: "Flights", weather: "Weather", places: "Places", fx: "Exchange rates" };

function ago(iso: string | null): string {
  if (!iso) return "not contacted yet";
  const m = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  return m < 1 ? "just now" : m < 60 ? `${m} min ago` : `${Math.round(m / 60)} h ago`;
}

export default function SettingsPage() {
  const { tripId = "" } = useParams();
  const status = useQuery({ queryKey: ["status", tripId], queryFn: () => api.status(tripId) });
  const prefs = usePrefs();

  return (
    <main className="flex-1 space-y-6 overflow-y-auto p-4">
      <section aria-labelledby="s-int">
        <h2 id="s-int" className="mb-2 text-lg font-semibold">Connections</h2>
        <ErrorNote error={status.error} />
        {status.data && (
          <>
            <p className="mb-2 text-sm text-slate-500">
              Assistant: <strong>{status.data.llm_provider}</strong> {status.data.llm_configured ? "✓ ready" : "✗ no API key set"} · Live data: <strong>{status.data.live_mode}</strong>
            </p>
            <ul className="divide-y divide-slate-200 rounded-xl border border-slate-200 bg-white dark:divide-slate-800 dark:border-slate-800 dark:bg-slate-900">
              {status.data.integrations.map((i) => (
                <li key={i.name} className="flex items-center justify-between gap-3 p-3 text-sm">
                  <span><span className="font-medium">{NAMES[i.name] ?? i.name}</span><br /><span className="text-slate-500">{i.provider}</span></span>
                  <span className="text-right text-slate-500">{i.mode === "mock" ? "sample data" : "live"}<br />{ago(i.last_contacted)}</span>
                </li>
              ))}
            </ul>
          </>
        )}
      </section>

      <section aria-labelledby="s-pref" className="space-y-3">
        <h2 id="s-pref" className="text-lg font-semibold">Preferences</h2>
        <div><label className={label} htmlFor="p-units">Units</label>
          <select id="p-units" className={field} value={prefs.units} onChange={(e) => setPrefs({ units: e.target.value as "metric" | "imperial" })}>
            <option value="metric">Metric (°C, km)</option><option value="imperial">Imperial (°F, miles)</option></select></div>
        <div><label className={label} htmlFor="p-cur">Display currency</label>
          <select id="p-cur" className={field} value={prefs.currency} onChange={(e) => setPrefs({ currency: e.target.value })}>
            {["USD", "EUR", "GBP", "JPY", "INR", "AUD", "CAD"].map((c) => <option key={c}>{c}</option>)}</select></div>
        <div><label className={label} htmlFor="p-lang">Answer language</label>
          <select id="p-lang" className={field} value={prefs.language} onChange={(e) => setPrefs({ language: e.target.value })}>
            {["English", "Español", "Français", "Deutsch", "日本語"].map((c) => <option key={c}>{c}</option>)}</select></div>
        <div><label className={label} htmlFor="p-theme">Appearance</label>
          <select id="p-theme" className={field} value={prefs.theme} onChange={(e) => setPrefs({ theme: e.target.value as "auto" | "light" | "dark" })}>
            <option value="auto">Automatic (dark after 8 PM)</option><option value="light">Light</option><option value="dark">Dark</option></select></div>
      </section>

      <section aria-labelledby="s-off">
        <h2 id="s-off" className="mb-2 text-lg font-semibold">Offline storage</h2>
        <p className="text-sm text-slate-500">Offline access is not enabled yet.</p>
      </section>

      <section aria-labelledby="s-priv">
        <h2 id="s-priv" className="mb-2 text-lg font-semibold">Privacy</h2>
        <ul className="list-disc space-y-1 pl-5 text-sm text-slate-600 dark:text-slate-300">
          <li>Your documents and API keys stay on the trip server, not on this phone.</li>
          <li>Passport, booking and card numbers are masked here until you tap Reveal, and are never sent to the assistant.</li>
          <li>Your questions and short passages from your documents are sent to the assistant provider (<strong>{status.data?.llm_provider ?? "…"}</strong>) to write answers.</li>
          <li>Live lookups (flights, weather, places, exchange rates) go to the services listed above.</li>
        </ul>
      </section>
    </main>
  );
}
