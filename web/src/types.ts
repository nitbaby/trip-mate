export interface Trip {
  id: string; name: string; destinations: string[]; start_date: string; end_date: string; timezone: string;
}
export interface KeyFact { index: number; label: string; value: string; sensitive: boolean }
export type DocStatus = "queued" | "processing" | "ready" | "failed";
export interface TripDoc {
  id: string; filename: string; doc_type: string | null; status: DocStatus; error: string | null;
  uploaded_at: string; key_facts: KeyFact[];
}
export type ItemType = "flight" | "hotel" | "reservation" | "activity" | "transit" | "note";
export interface ItineraryItem {
  id: string; trip_id: string; type: ItemType; title: string; start_at: string; end_at: string | null;
  location: string | null; notes: string | null; source: "user" | "agent"; document_id: string | null;
  conflicts_with?: string[];
}
export interface TripDetail extends Trip { itinerary: ItineraryItem[]; documents: TripDoc[] }
export interface Integration { name: string; provider: string; mode: string; last_contacted: string | null }
export interface StatusInfo { live_mode: string; llm_provider: string; llm_configured: boolean; integrations: Integration[] }
export interface ChunkView {
  chunk_id: string; document_id: string; document_name: string; page: number; text: string;
  surrounding: { id: string; page: number; text: string }[];
}
export interface StoredMessage { id: string; role: "user" | "assistant"; content: string; created_at: string }

// Spec 5.2 (itinerary_updated also carries undoId)
export type ChatEvent =
  | { type: "token"; text: string }
  | { type: "tool_start"; toolCallId: string; name: string; label: string }
  | { type: "tool_result"; toolCallId: string; ok: boolean; summary: string }
  | { type: "citation"; marker: string; docId: string; chunkId: string; label: string }
  | { type: "confidence"; level: "high" | "low" | "none" }
  | { type: "verify"; reason: string }
  | { type: "itinerary_updated"; itemId: string; action: "created" | "updated" | "deleted"; undoId?: string }
  | { type: "error"; code: string; message: string; retryable: boolean }
  | { type: "done"; messageId: string };

export interface ToolCall { id: string; name: string; label: string; status: "running" | "ok" | "failed"; summary?: string }
export interface Citation { marker: string; docId: string; chunkId: string; label: string }
export interface UserMessage { id: string; role: "user"; text: string }
export interface AssistantMessage {
  id: string; role: "assistant"; text: string; tools: ToolCall[]; citations: Record<string, Citation>;
  confidence?: "high" | "low" | "none"; verify?: string;
  itinerary: { itemId: string; action: string; undoId?: string }[];
  error?: { message: string; retryable: boolean };
  status: "streaming" | "done" | "error" | "stopped";
}
export type ChatMessage = UserMessage | AssistantMessage;
