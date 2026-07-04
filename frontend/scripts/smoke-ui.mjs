import { spawn } from "node:child_process";
import { mkdirSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { chromium } from "playwright-core";

const rootDir = resolve("..");
const backendDir = resolve(rootDir, "backend");
const backendPort = Number(process.env.SMOKE_BACKEND_PORT || 8810);
const frontendPort = Number(process.env.SMOKE_FRONTEND_PORT || 5810);
const backendUrl = `http://127.0.0.1:${backendPort}`;
const frontendUrl = `http://127.0.0.1:${frontendPort}`;
const chromePath =
  process.env.CHROME_PATH ||
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";

const children = [];

function spawnManaged(command, args, options) {
  const child = spawn(command, args, {
    stdio: ["ignore", "pipe", "pipe"],
    ...options,
    env: {
      ...process.env,
      ...options.env
    }
  });
  child.stdout.on("data", (chunk) => process.stdout.write(`[${options.name}] ${chunk}`));
  child.stderr.on("data", (chunk) => process.stderr.write(`[${options.name}] ${chunk}`));
  children.push(child);
  return child;
}

async function waitForHttp(url, label) {
  const started = Date.now();
  let lastError;
  while (Date.now() - started < 30000) {
    try {
      const response = await fetch(url);
      if (response.ok) return;
      lastError = new Error(`${label} returned ${response.status}`);
    } catch (error) {
      lastError = error;
    }
    await new Promise((resolveWait) => setTimeout(resolveWait, 500));
  }
  throw new Error(`Timed out waiting for ${label}: ${lastError?.message || "no response"}`);
}

async function expectText(locator, pattern, label) {
  await locator.waitFor({ timeout: 8000 });
  const text = await locator.textContent();
  if (!pattern.test(text || "")) {
    throw new Error(`${label} did not match ${pattern}. Saw: ${text}`);
  }
}

async function runSmoke() {
  spawnManaged(resolve(rootDir, ".venv/bin/python"), ["-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", String(backendPort)], {
    cwd: backendDir,
    name: "backend",
    env: {
      DEMO_MODE: "true",
      CASH_FLOOR: "5000",
      FRONTEND_ORIGINS: `${frontendUrl},http://localhost:${frontendPort}`
    }
  });

  spawnManaged("npm", ["run", "dev", "--", "--host", "127.0.0.1", "--port", String(frontendPort)], {
    cwd: resolve(rootDir, "frontend"),
    name: "frontend",
    env: {
      VITE_API_BASE: backendUrl
    }
  });

  await waitForHttp(`${backendUrl}/health`, "backend");
  await waitForHttp(frontendUrl, "frontend");

  const browser = await chromium.launch({
    executablePath: chromePath,
    headless: true
  });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  const browserErrors = [];
  page.on("pageerror", (error) => {
    browserErrors.push(error.message);
  });
  page.on("response", (response) => {
    const url = response.url();
    if (response.status() >= 400 && !url.endsWith("/favicon.ico")) {
      browserErrors.push(`${response.status()} ${url}`);
    }
  });

  try {
    await page.goto(frontendUrl, { waitUntil: "networkidle" });
    await page.getByRole("heading", { name: "Nero" }).waitFor();
    await page.locator(".recharts-wrapper").waitFor();
    const lineCount = await page.locator(".recharts-line-curve").count();
    if (lineCount < 3) throw new Error(`Expected at least 3 rendered forecast lines, saw ${lineCount}`);
    await expectText(page.locator(".chart-panel"), /\d+ Jul below floor|below floor/i, "forecast warning");

    await page.getByRole("button", { name: "$10k" }).click();
    await page.getByRole("button", { name: "Apply floor" }).click();
    await expectText(page.locator(".cash-floor-readout"), /\$10,000/, "cash floor readout");
    const settings = await page.evaluate((url) => fetch(`${url}/api/settings`).then((response) => response.json()), backendUrl);
    if (settings.cash_floor !== 10000) throw new Error(`Expected cash_floor 10000, saw ${settings.cash_floor}`);

    await page.getByRole("button", { name: /Check demo sync|Sync Xero/ }).click();
    await page.getByText(/Demo sync checked|Synced \d+ contacts/).waitFor();
    await page.getByRole("heading", { name: "Xero App Store" }).waitFor();
    await page.getByText("Sign Up with Xero").waitFor();
    await page.getByText("App Store listing").waitFor();

    await page.getByRole("button", { name: "Payers" }).click();
    await page.getByRole("heading", { name: "Payment performance" }).waitFor();
    await page.getByText("Open exposure").first().waitFor();

    await page.getByRole("button", { name: "Agent Queue" }).click();
    await page.getByRole("heading", { name: "Agent Queue" }).waitFor();
    await page.getByRole("button", { name: "Approve" }).first().click();
    await page.getByRole("button", { name: "Outbox" }).click();
    await page.getByRole("heading", { name: "Outbox" }).waitFor();
    await page.getByText(/Apex Corp|Cedar & Finch|Stonepath|Blue Harbor/).first().waitFor();

    await page.getByRole("button", { name: "Dashboard" }).click();
    await page.getByRole("button", { name: "Mark paid" }).first().click();
    await page.getByRole("button", { name: "Action Log" }).click();
    await page.getByText(/Payment received|Approved/).first().waitFor();

    if (browserErrors.length) {
      throw new Error(`Browser errors:\n${browserErrors.join("\n")}`);
    }
  } catch (error) {
    const dir = join(tmpdir(), "nero-smoke");
    mkdirSync(dir, { recursive: true });
    const screenshotPath = join(dir, `failure-${Date.now()}.png`);
    await page.screenshot({ path: screenshotPath, fullPage: true });
    error.message = `${error.message}\nScreenshot: ${screenshotPath}`;
    throw error;
  } finally {
    await browser.close();
  }
}

try {
  await runSmoke();
  console.log("UI smoke test passed");
} finally {
  for (const child of children.reverse()) {
    if (!child.killed) child.kill("SIGTERM");
  }
}
