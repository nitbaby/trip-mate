// Drives the real UI in desktop Chrome at phone size and saves screenshots (visual check, not a test suite).
import { chromium } from "@playwright/test";
import path from "node:path";
const out = process.argv[2] ?? "/tmp/tm-ui/shots";
const BASE = process.env.BASE_URL ?? "http://localhost:5173";
const samples = path.resolve("../samples");
const browser = await chromium.launch({ channel: "chrome" });
const ctx = await browser.newContext({ viewport: { width: 375, height: 812 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true, colorScheme: "light" });
const page = await ctx.newPage();
page.on("pageerror", (e) => console.log("PAGE ERROR:", e.message));
page.on("console", (m) => m.type() === "error" && console.log("CONSOLE ERROR:", m.text()));
const shot = (n) => page.screenshot({ path: `${out}/${n}.png` });

await page.goto(`${BASE}/`);
await shot("01-trips-empty");
await page.getByRole("button", { name: "New trip" }).click();
await page.getByLabel("Name").fill("Tokyo Dec 2026");
await page.getByLabel(/Destinations/).fill("Tokyo");
await page.getByLabel("Start").fill("2026-11-30");
await page.getByLabel("End").fill("2026-12-06");
await page.getByLabel("Timezone").fill("Asia/Tokyo");
await shot("02-trip-form");
await page.getByRole("button", { name: "Create trip" }).click();
await page.waitForURL(/\/docs$/);

await page.getByLabel("Choose documents to upload").setInputFiles(
  ["hotel_confirmation.txt", "flight_itinerary.txt", "japan_entry_rules.txt", "tokyo_guide.md"].map((f) => path.join(samples, f)));
await shot("03-docs-processing");
await page.waitForFunction(() => document.querySelectorAll("li").length >= 4 && ![...document.querySelectorAll("li span")].some((s) => /Reading|Queued/.test(s.textContent ?? "")), null, { timeout: 90000 });
await shot("04-docs-ready");
await page.getByRole("button", { name: /Reveal Passport number/ }).first().click();
await page.waitForTimeout(500);
await shot("05-docs-revealed");

await page.getByRole("link", { name: /Chat/ }).click();
await shot("06-chat-empty");
const ask = async (q, name) => {
  await page.getByLabel("Message").fill(q);
  await page.getByRole("button", { name: "Send" }).click();
  await page.waitForFunction(() => !document.querySelector(".tm-cursor") && document.querySelector('button[aria-label="Stop answering"]') === null, null, { timeout: 90000 });
  await page.waitForTimeout(300);
  await shot(name);
};
await ask("What time is check-out, and does the hotel include breakfast?", "07-chat-checkout");
await page.getByRole("button", { name: /^Source 1/ }).first().click();
await page.waitForTimeout(500);
await shot("08-source-drawer");
await page.keyboard.press("Escape");
await ask("What's the rule for bringing medication into Japan?", "09-chat-medication");
await ask("Is my 6 PM flight delayed?", "10-chat-flight");
await ask("Find a vegetarian place near my hotel that's open now.", "11-chat-places");
await ask("Add a dinner reservation at 8 PM to tomorrow's itinerary.", "12-chat-itinerary-undo");
await ask("how do I bake sourdough bread", "13-chat-notfound");

await page.getByRole("link", { name: /Itinerary/ }).click();
await page.waitForTimeout(600);
await shot("14-itinerary");
await page.getByRole("button", { name: "Add itinerary item" }).click();
await shot("15-itinerary-sheet");
await page.keyboard.press("Escape");
await page.getByRole("link", { name: /Settings/ }).click();
await page.waitForTimeout(500);
await shot("16-settings");
await ctx.close();

const dark = await browser.newContext({ viewport: { width: 375, height: 812 }, deviceScaleFactor: 2, isMobile: true, colorScheme: "dark" });
const p2 = await dark.newPage();
await p2.goto(`${BASE}/`);
await p2.getByRole("link").first().click();
await p2.getByRole("link", { name: /Chat/ }).click();
await p2.waitForTimeout(800);
await p2.screenshot({ path: `${out}/17-dark-chat.png` });
await browser.close();
console.log("done");
