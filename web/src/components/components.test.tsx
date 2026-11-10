import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "../api/client";
import { Markdown } from "../lib/markdown";
import { FactCard } from "../pages/DocsPage";
import type { Citation } from "../types";

afterEach(() => vi.useRealTimers());

describe("Markdown", () => {
  const cites: Record<string, Citation> = { "[1]": { marker: "[1]", docId: "d", chunkId: "c", label: "hotel.txt, p.1" } };

  it("renders citation chips that open the source, and hides unknown markers", async () => {
    const onCite = vi.fn();
    render(<Markdown text={"Check-out is **11 AM** [1]. Bogus [9]."} citations={cites} onCite={onCite} />);
    await userEvent.click(screen.getByRole("button", { name: "Source 1: hotel.txt, p.1" }));
    expect(onCite).toHaveBeenCalledWith(cites["[1]"]);
    expect(screen.getByText("11 AM").tagName).toBe("STRONG");
    expect(screen.queryByText("[9]")).toBeNull();
    expect(screen.queryByRole("button", { name: /Source 9/ })).toBeNull();
  });

  it("renders lists and never injects HTML", () => {
    const { container } = render(<Markdown text={"* one\n* two <img src=x onerror=alert(1)>"} citations={{}} onCite={() => {}} />);
    expect(container.querySelectorAll("li")).toHaveLength(2);
    expect(container.querySelector("img")).toBeNull();
    expect(screen.getByText(/two <img/)).toBeInTheDocument();
  });
});

describe("FactCard (DOC-05/06)", () => {
  const fact = { index: 3, label: "Passport number", value: "•••••••07", sensitive: true };

  it("masks by default, reveals on tap, and re-masks after 30 seconds", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.spyOn(api, "reveal").mockResolvedValue({ value: "P48213907", reveal_seconds: 30 });
    render(<FactCard docId="d1" fact={fact} />);
    expect(screen.getByTestId("fact-value")).toHaveTextContent("•••••••07");

    await act(async () => { screen.getByRole("button", { name: "Reveal Passport number" }).click(); });
    expect(api.reveal).toHaveBeenCalledWith("d1", 3);
    expect(screen.getByTestId("fact-value")).toHaveTextContent("P48213907");

    await act(async () => { vi.advanceTimersByTime(29_000); });
    expect(screen.getByTestId("fact-value")).toHaveTextContent("P48213907");
    await act(async () => { vi.advanceTimersByTime(2_000); });
    expect(screen.getByTestId("fact-value")).toHaveTextContent("•••••••07");
    expect(screen.getByRole("button", { name: "Reveal Passport number" })).toBeInTheDocument();
  });

  it("can be hidden early, and non-sensitive facts have no reveal button", async () => {
    vi.spyOn(api, "reveal").mockResolvedValue({ value: "P48213907", reveal_seconds: 30 });
    const { rerender } = render(<FactCard docId="d1" fact={fact} />);
    await userEvent.click(screen.getByRole("button", { name: /Reveal/ }));
    await userEvent.click(await screen.findByRole("button", { name: /Hide Passport/ }));
    expect(screen.getByTestId("fact-value")).toHaveTextContent("•••••••07");
    rerender(<FactCard docId="d1" fact={{ index: 0, label: "Check-out", value: "11:00 AM", sensitive: false }} />);
    expect(screen.queryByRole("button")).toBeNull();
  });
});
