import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import type { Citation } from "../types";
import { Sheet } from "./Sheet";
import { Spinner } from "./ui";

/** CHAT-03: the cited passage, its surrounding text, document name and page. */
export function SourceDrawer({ citation, onClose }: { citation: Citation; onClose: () => void }) {
  const q = useQuery({ queryKey: ["chunk", citation.docId, citation.chunkId], queryFn: () => api.chunk(citation.docId, citation.chunkId) });
  return (
    <Sheet title="Source" onClose={onClose}>
      {q.isLoading && <Spinner label="Loading source" />}
      {q.error && <p role="alert" className="text-red-600">{(q.error as Error).message}</p>}
      {q.data && (
        <div className="space-y-3">
          <p className="text-sm text-slate-500"><strong>{q.data.document_name}</strong> · page {q.data.page}</p>
          {q.data.surrounding.map((c) => (
            <p key={c.id} data-cited={c.id === q.data.chunk_id} className={`whitespace-pre-wrap rounded-lg p-3 text-sm ${
              c.id === q.data.chunk_id ? "border-l-4 border-indigo-500 bg-indigo-50 dark:bg-indigo-950" : "text-slate-500"}`}>
              {c.text}
            </p>
          ))}
          <p className="text-xs text-slate-500">Sensitive numbers in documents are masked.</p>
        </div>
      )}
    </Sheet>
  );
}
