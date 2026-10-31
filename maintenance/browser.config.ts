// Trusted launcher keeps the normal suite but uses the real application mode.
import base from "/work/playwright.config";
import { defineConfig } from "/work/node_modules/@playwright/test";

if (process.env.E2E_TEST_DATA !== "0") throw new Error("Real backend mode required");

export default defineConfig({
  ...base,
  testDir: "/work/tests/e2e",
  outputDir: "/work/test-results",
  reporter: [["list"], ["json", { outputFile: "/work/test-results/e2e-report.json" }]],
  use: { ...base.use, trace: "off", video: "off", screenshot: "off" },
  webServer: {
    cwd: "/work",
    command: "node /work/node_modules/next/dist/bin/next start -p 3100",
    url: "http://localhost:3100/api/health",
    reuseExistingServer: false,
    timeout: 120_000,
  },
});
