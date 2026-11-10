import type { ButtonHTMLAttributes } from "react";

export const field = "min-h-11 w-full rounded-lg border border-slate-300 bg-white px-3 text-base dark:border-slate-700 dark:bg-slate-800";
export const label = "mb-1 block text-sm font-medium text-slate-600 dark:text-slate-300";

export function Button({ variant = "primary", className = "", ...p }: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "ghost" | "danger" }) {
  const v = {
    primary: "bg-indigo-600 text-white disabled:bg-indigo-300",
    ghost: "bg-slate-200 text-slate-900 dark:bg-slate-800 dark:text-slate-100",
    danger: "bg-red-600 text-white",
  }[variant];
  return <button type="button" {...p} className={`min-h-11 rounded-lg px-4 text-base font-medium ${v} ${className}`} />;
}

export function ErrorNote({ error }: { error: unknown }) {
  if (!error) return null;
  return <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-700 dark:bg-red-950 dark:text-red-200">{(error as Error).message}</p>;
}

export function Spinner({ label = "Loading" }: { label?: string }) {
  return <p role="status" className="p-6 text-center text-sm text-slate-500">{label}…</p>;
}
