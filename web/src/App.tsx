import { useEffect } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { usePrefs } from "./lib/prefs";
import { isNight } from "./lib/time";
import ChatPage from "./pages/ChatPage";
import DocsPage from "./pages/DocsPage";
import ItineraryPage from "./pages/ItineraryPage";
import SettingsPage from "./pages/SettingsPage";
import TripLayout from "./pages/TripLayout";
import TripsPage from "./pages/TripsPage";

/** A11Y-05: dark by default after 8 PM local time or when the system is dark; Settings can force light/dark. */
function useTheme() {
  const { theme } = usePrefs();
  useEffect(() => {
    const apply = () => {
      const sysDark = window.matchMedia?.("(prefers-color-scheme: dark)").matches ?? false;
      const dark = theme === "dark" || (theme === "auto" && (sysDark || isNight()));
      document.documentElement.classList.toggle("dark", dark);
      document.querySelector('meta[name="theme-color"]')?.setAttribute("content", dark ? "#1e1b4b" : "#4f46e5");
    };
    apply();
    const id = setInterval(apply, 5 * 60_000);
    return () => clearInterval(id);
  }, [theme]);
}

export default function App() {
  useTheme();
  return (
    <div className="mx-auto flex h-dvh max-w-md flex-col bg-slate-50 text-slate-900 shadow-xl dark:bg-slate-950 dark:text-slate-100">
      <Routes>
        <Route path="/" element={<TripsPage />} />
        <Route path="/trips/:tripId" element={<TripLayout />}>
          <Route index element={<Navigate to="chat" replace />} />
          <Route path="chat" element={<ChatPage />} />
          <Route path="itinerary" element={<ItineraryPage />} />
          <Route path="docs" element={<DocsPage />} />
          <Route path="settings" element={<SettingsPage />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </div>
  );
}
