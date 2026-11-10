import { ApiError, errorFrom } from "../api/client";
import type { ChatEvent } from "../types";

/** Split a buffer into complete SSE events (blank-line separated) and the unparsed remainder. */
export function parseSse(buffer: string): { events: ChatEvent[]; rest: string } {
  const blocks = buffer.split(/\r?\n\r?\n/);
  const rest = blocks.pop() ?? "";
  const events: ChatEvent[] = [];
  for (const block of blocks) {
    const data = block.split(/\r?\n/).filter((l) => l.startsWith("data:")).map((l) => l.slice(5).replace(/^ /, ""));
    if (!data.length) continue; // comments / pings
    try {
      events.push(JSON.parse(data.join("\n")) as ChatEvent);
    } catch { /* skip malformed event */ }
  }
  return { events, rest };
}

/** POST a chat message and yield typed events as they stream in (CHAT-01). Abort via the signal (CHAT-06). */
export async function* streamChat(
  tripId: string, message: string, conversationId: string, signal: AbortSignal,
  preferences?: Record<string, string>,
): AsyncGenerator<ChatEvent> {
  let res: Response;
  try {
    res = await fetch(`/api/trips/${tripId}/chat`, {
      method: "POST", signal, headers: { "content-type": "application/json" },
      body: JSON.stringify({ message, conversationId, preferences }),
    });
  } catch (e) {
    if ((e as Error).name === "AbortError") throw e;
    throw new ApiError("EXTERNAL_UNAVAILABLE", "Can't reach the TripMate server.", true);
  }
  if (!res.ok || !res.body) throw await errorFrom(res);
  const reader = res.body.getReader();
  const dec = new TextDecoder();
  let buf = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    const { events, rest } = parseSse(buf);
    buf = rest;
    for (const e of events) yield e;
  }
  buf += dec.decode();
  for (const e of parseSse(buf + "\n\n").events) yield e;
}
