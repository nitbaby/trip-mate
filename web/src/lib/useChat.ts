import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError } from "../api/client";
import { useToast } from "../components/Toast";
import type { AssistantMessage, ChatEvent, ChatMessage } from "../types";
import { applyEvent, newAssistant, plainText } from "./chatReducer";
import { getPrefs } from "./prefs";
import { streamChat } from "./sse";

const convKey = (tripId: string) => `tm.conv.${tripId}`;
const newId = () => crypto.randomUUID().replace(/-/g, "").slice(0, 12);
const UNDO_MS = 10_000; // ITIN-05

export function useChat(tripId: string) {
  const qc = useQueryClient();
  const toast = useToast();
  const [conv, setConv] = useState(() => localStorage.getItem(convKey(tripId)) ?? "");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [busy, setBusy] = useState(false);
  const [announce, setAnnounce] = useState("");
  const abort = useRef<AbortController | null>(null);
  const loaded = useRef(false);

  // restore history for an existing conversation
  const history = useQuery({ queryKey: ["messages", tripId, conv], queryFn: () => api.messages(tripId, conv), enabled: !!conv });
  useEffect(() => {
    if (loaded.current || !history.data) return;
    loaded.current = true;
    setMessages((cur) => cur.length ? cur : history.data.map((m): ChatMessage =>
      m.role === "user" ? { id: m.id, role: "user", text: m.content }
        : { ...newAssistant(m.id), text: m.content, status: "done" }));
  }, [history.data]);
  useEffect(() => () => abort.current?.abort(), []);

  const patchLast = (fn: (m: AssistantMessage) => AssistantMessage) =>
    setMessages((ms) => {
      const last = ms[ms.length - 1];
      return last?.role === "assistant" ? [...ms.slice(0, -1), fn(last)] : ms;
    });

  const onSideEffects = useCallback((e: ChatEvent) => {
    if (e.type === "itinerary_updated") {
      qc.invalidateQueries({ queryKey: ["itinerary", tripId] });
      if (e.undoId) {
        toast({
          message: `Itinerary ${e.action} by TripMate`, duration: UNDO_MS,
          action: { label: "Undo", onClick: async () => {
            try { await api.undo(tripId, e.undoId!); qc.invalidateQueries({ queryKey: ["itinerary", tripId] }); toast({ message: "Change undone" }); }
            catch (err) { toast({ message: (err as Error).message }); }
          } },
        });
      }
    }
  }, [qc, toast, tripId]);

  const send = useCallback(async (text: string) => {
    text = text.trim();
    if (!text || busy) return;
    let id = conv;
    if (!id) { id = newId(); localStorage.setItem(convKey(tripId), id); setConv(id); loaded.current = true; }
    const ctl = new AbortController();
    abort.current = ctl;
    setBusy(true);
    setMessages((ms) => [...ms, { id: `u${Date.now()}`, role: "user", text }, newAssistant(`a${Date.now()}`)]);
    const p = getPrefs();
    try {
      for await (const ev of streamChat(tripId, text, id, ctl.signal, { units: p.units, currency: p.currency, language: p.language })) {
        patchLast((m) => applyEvent(m, ev));
        onSideEffects(ev);
        if (ev.type === "done") setMessages((ms) => { const l = ms[ms.length - 1]; if (l?.role === "assistant") setAnnounce(plainText(l.text)); return ms; });
      }
      patchLast((m) => m.status === "streaming"
        ? { ...m, status: "error", error: { message: "The connection was interrupted.", retryable: true } } : m);
    } catch (e) {
      if ((e as Error).name === "AbortError") patchLast((m) => ({ ...m, status: "stopped" }));
      else {
        const a = e instanceof ApiError ? e : new ApiError("AGENT_FAILED", "Something went wrong.", true);
        patchLast((m) => applyEvent(m, { type: "error", code: a.code, message: a.message, retryable: a.retryable }));
      }
    } finally {
      setBusy(false);
      abort.current = null;
    }
  }, [busy, conv, onSideEffects, tripId]);

  const stop = useCallback(() => abort.current?.abort(), []);
  const retry = useCallback(() => {
    const lastUser = [...messages].reverse().find((m) => m.role === "user");
    if (lastUser && lastUser.role === "user") void send(lastUser.text);
  }, [messages, send]);
  const reset = useCallback(() => {
    abort.current?.abort();
    localStorage.removeItem(convKey(tripId));
    loaded.current = true;
    setConv(""); setMessages([]); setAnnounce("");
  }, [tripId]);

  return { messages, busy, send, stop, retry, reset, announce };
}
