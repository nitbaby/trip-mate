import { useQuery } from "@tanstack/react-query";
import { Link, NavLink, Outlet, useParams } from "react-router-dom";
import { api } from "../api/client";

const tabs = [
  { to: "chat", label: "Chat", icon: "💬" },
  { to: "itinerary", label: "Itinerary", icon: "🗓️" },
  { to: "docs", label: "Docs", icon: "📄" },
  { to: "settings", label: "Settings", icon: "⚙️" },
];

export default function TripLayout() {
  const { tripId = "" } = useParams();
  const trip = useQuery({ queryKey: ["trip", tripId], queryFn: () => api.trip(tripId),
    // poll while any document is still being read (DOC-02)
    refetchInterval: (q) => (q.state.data?.documents.some((d) => d.status === "queued" || d.status === "processing") ? 1500 : false),
  });

  if (trip.isError) {
    return (
      <main className="p-6 text-center">
        <p role="alert" className="mb-4">{(trip.error as Error).message}</p>
        <Link to="/" className="font-medium text-indigo-600 underline">Back to trips</Link>
      </main>
    );
  }
  return (
    <>
      <header className="flex items-center gap-2 bg-indigo-600 px-2 pt-[env(safe-area-inset-top)] text-white dark:bg-indigo-950">
        <Link to="/" aria-label="All trips" className="flex size-11 items-center justify-center text-xl">←</Link>
        <div className="min-w-0 flex-1 py-2">
          <h1 className="truncate text-base font-semibold leading-tight">{trip.data?.name ?? "Loading…"}</h1>
          {trip.data && <p className="truncate text-xs opacity-80">{trip.data.destinations.join(", ")} · {trip.data.start_date} → {trip.data.end_date}</p>}
        </div>
      </header>
      <div className="flex min-h-0 flex-1 flex-col">
        <Outlet context={{ trip: trip.data }} />
      </div>
      <nav aria-label="Main" className="flex border-t border-slate-200 bg-white pb-[env(safe-area-inset-bottom)] dark:border-slate-800 dark:bg-slate-900">
        {tabs.map((t) => (
          <NavLink key={t.to} to={t.to} className={({ isActive }) =>
            `flex min-h-14 flex-1 flex-col items-center justify-center text-xs ${isActive ? "font-semibold text-indigo-600 dark:text-indigo-300" : "text-slate-500"}`}>
            <span aria-hidden="true" className="text-lg leading-none">{t.icon}</span>{t.label}
          </NavLink>
        ))}
      </nav>
    </>
  );
}
