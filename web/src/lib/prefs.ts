import { useSyncExternalStore } from "react";

export interface Prefs { units: "metric" | "imperial"; currency: string; language: string; theme: "auto" | "light" | "dark" }
const KEY = "tm.prefs";
const DEFAULTS: Prefs = { units: "metric", currency: "USD", language: "English", theme: "auto" };
const listeners = new Set<() => void>();
let cache: Prefs | null = null;

function read(): Prefs {
  if (cache) return cache;
  try { cache = { ...DEFAULTS, ...JSON.parse(localStorage.getItem(KEY) ?? "{}") }; } catch { cache = DEFAULTS; }
  return cache!;
}
export function setPrefs(p: Partial<Prefs>) {
  cache = { ...read(), ...p };
  localStorage.setItem(KEY, JSON.stringify(cache));
  listeners.forEach((l) => l());
}
export const getPrefs = read;
export function usePrefs(): Prefs {
  return useSyncExternalStore((cb) => { listeners.add(cb); return () => listeners.delete(cb); }, read);
}
