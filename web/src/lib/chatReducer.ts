import type { AssistantMessage, ChatEvent } from "../types";

export const newAssistant = (id: string): AssistantMessage => ({
  id, role: "assistant", text: "", tools: [], agents: [], citations: {}, itinerary: [], status: "streaming",
});

/** Pure: fold one streamed event into the assistant message (spec 5.2 client behaviour). */
export function applyEvent(m: AssistantMessage, e: ChatEvent): AssistantMessage {
  switch (e.type) {
    case "token":
      return { ...m, text: m.text + e.text };
    case "agent_start":
      return { ...m, agents: [...m.agents, { name: e.agent, label: e.label, status: "running" }] };
    case "agent_end":
      return { ...m, agents: m.agents.map((a) => (a.name === e.agent ? { ...a, status: "done" } : a)) };
    case "verified":
      return { ...m, verification: { checked: e.checked, unsupported: e.unsupported } };
    case "tool_start":
      return { ...m, tools: [...m.tools, { id: e.toolCallId, name: e.name, label: e.label, status: "running", agent: e.agent }] };
    case "tool_result":
      return {
        ...m,
        tools: m.tools.map((t) => (t.id === e.toolCallId ? { ...t, status: e.ok ? "ok" : "failed", summary: e.summary } : t)),
      };
    case "citation":
      return { ...m, citations: { ...m.citations, [e.marker]: { marker: e.marker, docId: e.docId, chunkId: e.chunkId, label: e.label } } };
    case "confidence":
      return { ...m, confidence: e.level };
    case "verify":
      return { ...m, verify: e.reason };
    case "itinerary_updated":
      return { ...m, itinerary: [...m.itinerary, { itemId: e.itemId, action: e.action, undoId: e.undoId }] };
    case "error":
      return { ...m, status: "error", error: { message: e.message, retryable: e.retryable } };
    case "done":
      return { ...m, id: e.messageId, status: "done" };
  }
}

/** Plain text of an answer for the screen-reader announcement (markers and markdown removed). */
export function plainText(text: string): string {
  return text.replace(/\[\d+\]/g, "").replace(/\*\*?([^*]+)\*\*?/g, "$1").replace(/^\s*[*-]\s+/gm, "").replace(/\s+/g, " ").trim();
}

/** The banner shows for low/none confidence (CHAT-02). */
export const needsBanner = (m: AssistantMessage) => m.confidence === "low" || m.confidence === "none";
