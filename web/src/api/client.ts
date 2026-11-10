import type { ChunkView, ItineraryItem, StatusInfo, StoredMessage, Trip, TripDetail, TripDoc } from "../types";

export class ApiError extends Error {
  constructor(public code: string, message: string, public retryable: boolean, public status = 0) {
    super(message);
  }
}

export async function errorFrom(res: Response): Promise<ApiError> {
  try {
    const b = await res.json();
    if (b?.error) return new ApiError(b.error.code, b.error.message, !!b.error.retryable, res.status);
  } catch { /* not JSON */ }
  return new ApiError("EXTERNAL_UNAVAILABLE", `Request failed (${res.status})`, res.status >= 500, res.status);
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, init);
  } catch {
    throw new ApiError("EXTERNAL_UNAVAILABLE", "Can't reach the TripMate server.", true);
  }
  if (!res.ok) throw await errorFrom(res);
  return res.status === 204 ? (undefined as T) : ((await res.json()) as T);
}

const json = (method: string, body?: unknown): RequestInit => ({
  method, headers: { "content-type": "application/json" }, body: body === undefined ? undefined : JSON.stringify(body),
});

export type ItemInput = Partial<Omit<ItineraryItem, "id" | "trip_id" | "source" | "conflicts_with">>;

export const api = {
  trips: () => req<Trip[]>("/api/trips"),
  createTrip: (t: Omit<Trip, "id">) => req<Trip>("/api/trips", json("POST", t)),
  trip: (id: string) => req<TripDetail>(`/api/trips/${id}`),
  itinerary: (id: string) => req<ItineraryItem[]>(`/api/trips/${id}/itinerary`),
  createItem: (id: string, b: ItemInput) => req<ItineraryItem>(`/api/trips/${id}/itinerary`, json("POST", b)),
  updateItem: (id: string, itemId: string, b: ItemInput) =>
    req<ItineraryItem>(`/api/trips/${id}/itinerary/${itemId}`, json("PATCH", b)),
  deleteItem: (id: string, itemId: string) => req<void>(`/api/trips/${id}/itinerary/${itemId}`, { method: "DELETE" }),
  undo: (id: string, undoId: string) => req<unknown>(`/api/trips/${id}/undo/${undoId}`, { method: "POST" }),
  upload: (id: string, file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return req<{ id: string; status: string }>(`/api/trips/${id}/documents`, { method: "POST", body: fd });
  },
  deleteDoc: (id: string, docId: string) => req<void>(`/api/trips/${id}/documents/${docId}`, { method: "DELETE" }),
  reveal: (docId: string, index: number) =>
    req<{ value: string; reveal_seconds: number }>(`/api/documents/${docId}/facts/${index}/reveal`),
  chunk: (docId: string, chunkId: string) => req<ChunkView>(`/api/documents/${docId}/chunks/${chunkId}`),
  status: (id: string) => req<StatusInfo>(`/api/trips/${id}/status`),
  messages: (id: string, conversationId: string) =>
    req<StoredMessage[]>(`/api/trips/${id}/conversations/${conversationId}/messages`),
};
export type { TripDoc };
