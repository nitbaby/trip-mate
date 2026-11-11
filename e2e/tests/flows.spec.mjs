// Five core flows on the demo LLM (a rule-based stand-in: answers are deterministic, so the checks are about the
// app: upload, citations + source drawer, live data, itinerary write + undo, and honest "not found").
import { expect, test } from "@playwright/test";
import path from "node:path";

const samples = path.resolve(import.meta.dirname, "../../samples");
const SAMPLES = ["hotel_confirmation.txt", "flight_itinerary.txt", "japan_entry_rules.txt", "tokyo_guide.md"];
test.describe.configure({ mode: "serial" });

let page;
test.beforeAll(async ({ browser }) => {
  page = await (await browser.newContext({ viewport: { width: 375, height: 812 }, isMobile: true, hasTouch: true })).newPage();
  page.on("pageerror", (e) => { throw new Error(`page error: ${e.message}`); });
});
test.afterAll(async () => { await page.context().close(); });

const ask = async (q) => {
  await page.getByLabel("Message").fill(q);
  await page.getByRole("button", { name: "Send" }).click();
  await expect(page.locator('button[aria-label="Stop answering"]')).toHaveCount(0, { timeout: 60_000 });
  await expect(page.locator(".tm-cursor")).toHaveCount(0);
};

test("1. create a trip and upload documents; sensitive values are masked until revealed", async () => {
  await page.goto("/");
  await page.getByRole("button", { name: "New trip" }).click();
  await page.getByLabel("Name").fill("E2E Tokyo");
  await page.getByLabel(/Destinations/).fill("Tokyo");
  await page.getByLabel("Start").fill("2026-11-30");
  await page.getByLabel("End").fill("2026-12-06");
  await page.getByLabel("Timezone").fill("Asia/Tokyo");
  await page.getByRole("button", { name: "Create trip" }).click();
  await page.waitForURL(/\/docs$/);
  await page.getByLabel("Choose documents to upload").setInputFiles(SAMPLES.map((f) => path.join(samples, f)));
  await expect(page.locator("li").filter({ hasText: /Reading|Queued/ })).toHaveCount(0, { timeout: 90_000 });
  await expect(page.locator("li")).toHaveCount(4);
  await expect(page.getByText("P48213907")).toHaveCount(0); // masked by default
  await page.getByRole("button", { name: /Reveal Passport number/ }).first().click();
  await expect(page.getByText("P48213907").first()).toBeVisible();
});

test("2. a document question is answered with a citation chip that opens the source", async () => {
  await page.getByRole("link", { name: /Chat/ }).click();
  await ask("What time is check-out, and does the hotel include breakfast?");
  // the demo model only echoes the best passages (it is not an AI), so check the app's behaviour, not the exact fact
  await expect(page.getByText("Documents agent")).toBeVisible();
  await expect(page.getByText(/sources? checked against your documents/)).toBeVisible();
  await expect(page.getByText(/Low confidence/)).toHaveCount(0);
  await page.getByRole("button", { name: /^Source 1/ }).first().click();
  await expect(page.getByText(/Breakfast is included|Check-out: 11:00 AM/).first()).toBeVisible(); // the drawer shows the original passage
  await page.getByRole("button", { name: "Close" }).first().click();
});

test("3. a live question calls the flight tool and shows the delay", async () => {
  await ask("Is my 6 PM flight delayed?");
  await expect(page.getByText(/35 min/).filter({ visible: true }).first()).toBeVisible(); // the collapsed tool card also has the text
});

test("4. the agent adds an itinerary item, the item shows on the itinerary page, and undo removes it", async () => {
  await ask("Add a dinner reservation at 8 PM to tomorrow's itinerary.");
  await expect(page.getByRole("button", { name: "Undo" })).toBeVisible();
  await page.getByRole("link", { name: /Itinerary/ }).click();
  await expect(page.getByText(/dinner/i).first()).toBeVisible();
  await page.getByRole("link", { name: /Chat/ }).click();
  await page.getByRole("button", { name: "Undo" }).last().click();
  await page.getByRole("link", { name: /Itinerary/ }).click();
  await expect(page.getByText(/dinner/i)).toHaveCount(0);
});

test("5. a question the documents cannot really answer is flagged with the low-confidence banner", async () => {
  // the demo model cannot refuse (it echoes passages), so this checks the app's own guard; real-model refusals are in the eval set
  await page.getByRole("link", { name: /Chat/ }).click();
  await ask("What is the Wi-Fi password at the airport lounge?");
  await expect(page.getByText(/Low confidence: this may not be fully supported/)).toBeVisible();
  await expect(page.getByText("P48213907")).toHaveCount(0); // the masked passport value never reaches the chat
});
