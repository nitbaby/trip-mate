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
export interface StatusInfo {
  live_mode: string; llm_provider: string; llm_configured: boolean; integrations: Integration[];
  llm_limits?: { rpm: number; daily_limit: number; requests_today: number | null; model: string } | null;
}
export interface ChunkView {
  chunk_id: string; document_id: string; document_name: string; page: number; text: string;
  surrounding: { id: string; page: number; text: string }[];
}
export interface StoredMessage { id: string; role: "user" | "assistant"; content: string; created_at: string }

// Spec 5.2 (itinerary_updated also carries undoId)
export type ChatEvent =
  | { type: "token"; text: string }
  | { type: "agent_start"; agent: string; label: string }
  | { type: "agent_end"; agent: string }
  | { type: "tool_start"; toolCallId: string; name: string; label: string; agent?: string }
  | { type: "tool_result"; toolCallId: string; ok: boolean; summary: string; agent?: string }
  | { type: "verified"; checked: number; unsupported: number }
  | { type: "citation"; marker: string; docId: string; chunkId: string; label: string }
  | { type: "confidence"; level: "high" | "low" | "none" }
  | { type: "verify"; reason: string }
  | { type: "itinerary_updated"; itemId: string; action: "created" | "updated" | "deleted"; undoId?: string }
  | { type: "error"; code: string; message: string; retryable: boolean }
  | { type: "waiting"; seconds: number; reason: "rate_limit" | "retry"; agent?: string }
  | { type: "done"; messageId: string; agentMode?: "single" | "multi"; llmCalls?: number; toolCalls?: number; quota?: { used: number; limit: number } };

export interface ToolCall { id: string; name: string; label: string; status: "running" | "ok" | "failed"; summary?: string; agent?: string }
export interface AgentRun { name: string; label: string; status: "running" | "done" }
export interface Citation { marker: string; docId: string; chunkId: string; label: string }
export interface UserMessage { id: string; role: "user"; text: string }
export interface AssistantMessage {
  id: string; role: "assistant"; text: string; tools: ToolCall[]; agents: AgentRun[]; citations: Record<string, Citation>;
  verification?: { checked: number; unsupported: number };
  waiting?: { seconds: number; reason: "rate_limit" | "retry" };   // queued for the LLM rate limit / backing off
  quota?: { used: number; limit: number };                        // daily LLM request budget, when one applies
  confidence?: "high" | "low" | "none"; verify?: string;
  itinerary: { itemId: string; action: string; undoId?: string }[];
  error?: { message: string; retryable: boolean };
  status: "streaming" | "done" | "error" | "stopped";
}
export type ChatMessage = UserMessage | AssistantMessage;
