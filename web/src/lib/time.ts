// Itinerary times are naive local strings ("2026-12-02T20:00:00") in the trip's timezone.
// They are split as strings, never run through Date, so the browser's timezone can't shift them.

export function todayIn(tz: string, now = new Date()): string {
  try {
    return new Intl.DateTimeFormat("en-CA", { timeZone: tz, year: "numeric", month: "2-digit", day: "2-digit" }).format(now);
  } catch {
    return now.toISOString().slice(0, 10);
  }
}

export const splitLocal = (iso: string) => ({ date: iso.slice(0, 10), time: iso.slice(11, 16) });

export function formatTime(hhmm: string): string {
  const [h, m] = hhmm.split(":").map(Number);
  return `${((h + 11) % 12) + 1}:${String(m).padStart(2, "0")} ${h < 12 ? "AM" : "PM"}`;
}

export function formatDay(date: string): string {
  const d = new Date(`${date}T12:00:00Z`);
  return new Intl.DateTimeFormat("en-GB", { weekday: "short", day: "numeric", month: "short", timeZone: "UTC" }).format(d);
}

export function groupByDay<T extends { start_at: string }>(items: T[]): { date: string; items: T[] }[] {
  const sorted = [...items].sort((a, b) => a.start_at.localeCompare(b.start_at));
  const out: { date: string; items: T[] }[] = [];
  for (const it of sorted) {
    const date = it.start_at.slice(0, 10);
    const last = out[out.length - 1];
    if (last && last.date === date) last.items.push(it);
    else out.push({ date, items: [it] });
  }
  return out;
}

/** ITIN-01: the day to scroll to: today if it has items, else the next day with items, else the last one. */
export function focusDay(days: string[], today: string): string | undefined {
  return days.find((d) => d >= today) ?? days[days.length - 1];
}

/** A11Y-05: dark after 8 PM until 6 AM local time. */
export const isNight = (now = new Date()) => now.getHours() >= 20 || now.getHours() < 6;

export const toInputValue = (iso: string | null) => (iso ? iso.slice(0, 16) : "");
export const fromInputValue = (v: string) => (v ? `${v}:00` : null);
