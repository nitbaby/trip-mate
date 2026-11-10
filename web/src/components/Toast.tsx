import { createContext, useCallback, useContext, useRef, useState, type ReactNode } from "react";

interface ToastInput { message: string; action?: { label: string; onClick: () => void }; duration?: number }
interface ToastItem extends ToastInput { id: number }
const Ctx = createContext<(t: ToastInput) => void>(() => {});
export const useToast = () => useContext(Ctx);

/** Toasts sit above the bottom nav. role=status so screen readers announce them (undo toast, ITIN-05). */
export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const next = useRef(1);
  const dismiss = useCallback((id: number) => setItems((l) => l.filter((t) => t.id !== id)), []);
  const show = useCallback((t: ToastInput) => {
    const id = next.current++;
    setItems((l) => [...l, { ...t, id }]);
    setTimeout(() => dismiss(id), t.duration ?? 4000);
  }, [dismiss]);

  return (
    <Ctx.Provider value={show}>
      {children}
      <div className="pointer-events-none fixed inset-x-0 bottom-20 z-50 mx-auto flex max-w-md flex-col gap-2 px-3" role="status" aria-live="polite">
        {items.map((t) => (
          <div key={t.id} className="pointer-events-auto overflow-hidden rounded-xl bg-slate-900 text-white shadow-lg dark:bg-slate-100 dark:text-slate-900">
            <div className="flex items-center justify-between gap-3 px-4 py-3">
              <span className="text-sm">{t.message}</span>
              {t.action && (
                <button type="button" className="min-h-11 rounded-lg px-3 text-sm font-semibold text-indigo-300 dark:text-indigo-700"
                  onClick={() => { t.action!.onClick(); dismiss(t.id); }}>
                  {t.action.label}
                </button>
              )}
            </div>
            {t.action && <div className="h-1 bg-indigo-400" style={{ animation: `tm-shrink ${(t.duration ?? 4000)}ms linear forwards` }} />}
          </div>
        ))}
      </div>
    </Ctx.Provider>
  );
}
