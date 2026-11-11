// E2E for the five core flows. Starts its OWN backend (:8010, demo LLM, fresh temp data dir) and web dev server (:5180):
// never touches data/ or the servers on :8000 / :5173. Run with `make e2e` (needs Node 22 and system Chrome).
import { defineConfig } from "@playwright/test";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), "tm-e2e-"));
const root = path.resolve(import.meta.dirname, "..");

export default defineConfig({
  testDir: "./tests",
  timeout: 90_000,
  workers: 1,
  fullyParallel: false,
  reporter: [["list"]],
  use: {
    baseURL: "http://localhost:5180",
    channel: "chrome",
    viewport: { width: 375, height: 812 },
    isMobile: true,
    hasTouch: true,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  webServer: [
    {
      command: `${root}/.venv/bin/uvicorn app.main:app --port 8010`,
      cwd: path.join(root, "backend"),
      url: "http://localhost:8010/api/health",
      reuseExistingServer: false,
      timeout: 60_000,
      env: { TRIPMATE_DATA_DIR: dataDir, LLM_PROVIDER: "demo", LIVE_MODE: "mock", AGENT_MODE: "multi" },
    },
    {
      command: "npx vite --port 5180 --strictPort",
      cwd: path.join(root, "web"),
      url: "http://localhost:5180",
      reuseExistingServer: false,
      timeout: 60_000,
      env: { VITE_API_TARGET: "http://localhost:8010" },
    },
  ],
});
