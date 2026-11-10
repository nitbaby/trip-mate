import { describe, expect, it } from "vitest";
import { applyEvent, newAssistant, needsBanner, plainText } from "./chatReducer";
import { parseSse } from "./sse";
import { focusDay, formatDay, formatTime, groupByDay, isNight, splitLocal, todayIn } from "./time";
import type { ChatEvent } from "../types";

const sse = (e: object) => `data: ${JSON.stringify(e)}\r\n\r\n`;

describe("parseSse", () => {
  it("parses complete events and keeps a partial remainder", () => {
    const a = sse({ type: "token", text: "Hi" });
    const b = sse({ type: "done", messageId: "m1" });
    const r = parseSse(a + b.slice(0, 10));
    expect(r.events).toEqual([{ type: "token", text: "Hi" }]);
    const r2 = parseSse(r.rest + b.slice(10));
    expect(r2.events).toEqual([{ type: "done", messageId: "m1" }]);
  });
  it("ignores pings and malformed data", () => {
    expect(parseSse(": ping\r\n\r\ndata: {oops\r\n\r\n" + sse({ type: "token", text: "x" })).events).toHaveLength(1);
  });
  it("handles LF-only separators and multi-byte text", () => {
    const r = parseSse(`data: ${JSON.stringify({ type: "token", text: "東京" })}\n\n`);
    expect(r.events[0]).toEqual({ type: "token", text: "東京" });
  });
});

describe("applyEvent", () => {
  const run = (events: ChatEvent[]) => events.reduce(applyEvent, newAssistant("tmp"));
  it("builds a full answer", () => {
    const m = run([
      { type: "tool_start", toolCallId: "t1", name: "search_docs", label: "Searching" },
      { type: "tool_result", toolCallId: "t1", ok: true, summary: "3 passages" },
      { type: "token", text: "Check-out is 11 " }, { type: "token", text: "AM [1]." },
      { type: "citation", marker: "[1]", docId: "d", chunkId: "c", label: "hotel.txt, p.1" },
      { type: "confidence", level: "high" }, { type: "verify", reason: "Check officially" },
      { type: "itinerary_updated", itemId: "i1", action: "created", undoId: "u1" },
      { type: "done", messageId: "m9" },
    ]);
    expect(m.text).toBe("Check-out is 11 AM [1].");
    expect(m.tools[0]).toMatchObject({ status: "ok", summary: "3 passages" });
    expect(m.citations["[1]"].chunkId).toBe("c");
    expect(m).toMatchObject({ id: "m9", status: "done", confidence: "high", verify: "Check officially" });
    expect(m.itinerary[0].undoId).toBe("u1");
    expect(needsBanner(m)).toBe(false);
  });
  it("tracks agents, groups tools under them and records the citation check", () => {
    const m = run([
      { type: "agent_start", agent: "docs", label: "Documents agent" },
      { type: "tool_start", toolCallId: "t1", name: "search_docs", label: "Searching", agent: "docs" },
      { type: "tool_result", toolCallId: "t1", ok: true, summary: "2 passages", agent: "docs" },
      { type: "agent_end", agent: "docs" },
      { type: "agent_start", agent: "composer", label: "Composing the answer" },
      { type: "verified", checked: 2, unsupported: 1 },
    ]);
    expect(m.agents).toEqual([
      { name: "docs", label: "Documents agent", status: "done" },
      { name: "composer", label: "Composing the answer", status: "running" },
    ]);
    expect(m.tools[0]).toMatchObject({ agent: "docs", status: "ok" });
    expect(m.verification).toEqual({ checked: 2, unsupported: 1 });
  });
  it("keeps partial text on error and flags low confidence", () => {
    const m = run([{ type: "token", text: "Partial" }, { type: "error", code: "AGENT_FAILED", message: "busy", retryable: true }]);
    expect(m).toMatchObject({ text: "Partial", status: "error", error: { retryable: true } });
    expect(needsBanner({ ...m, confidence: "none" })).toBe(true);
  });
  it("plainText strips markers and markdown", () => {
    expect(plainText("**Check-out** is 11 [1].\n* Breakfast [2]")).toBe("Check-out is 11 . Breakfast");
  });
});

describe("time helpers", () => {
  it("splits and formats local times without timezone shifts", () => {
    expect(splitLocal("2026-12-02T20:00:00")).toEqual({ date: "2026-12-02", time: "20:00" });
    expect(formatTime("20:00")).toBe("8:00 PM");
    expect(formatTime("00:05")).toBe("12:05 AM");
    expect(formatTime("12:30")).toBe("12:30 PM");
    expect(formatDay("2026-12-02")).toBe("Wed 2 Dec");
  });
  it("todayIn respects the trip timezone", () => {
    const t = new Date("2026-11-10T18:00:00Z");
    expect(todayIn("Asia/Tokyo", t)).toBe("2026-11-11");
    expect(todayIn("America/Los_Angeles", t)).toBe("2026-11-10");
  });
  it("groups by day and picks the day to open on (ITIN-01)", () => {
    const g = groupByDay([{ start_at: "2026-12-03T09:00:00" }, { start_at: "2026-12-01T20:00:00" }, { start_at: "2026-12-01T08:00:00" }]);
    expect(g.map((d) => [d.date, d.items.length])).toEqual([["2026-12-01", 2], ["2026-12-03", 1]]);
    const days = g.map((d) => d.date);
    expect(focusDay(days, "2026-12-01")).toBe("2026-12-01");
    expect(focusDay(days, "2026-12-02")).toBe("2026-12-03");
    expect(focusDay(days, "2027-01-01")).toBe("2026-12-03");
    expect(focusDay([], "2026-12-01")).toBeUndefined();
  });
  it("night mode is 8 PM to 6 AM", () => {
    const at = (h: number) => new Date(2026, 0, 1, h, 0);
    expect([isNight(at(19)), isNight(at(20)), isNight(at(5)), isNight(at(6))]).toEqual([false, true, true, false]);
  });
});
