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
const smokeDbPath = join(tmpdir(), `nero-smoke-${process.pid}.db`);
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
      DEMO_MODE: "false",
      CASH_FLOOR: "42000",
      NERO_DB_PATH: smokeDbPath,
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
  const seedResponse = await fetch(`${backendUrl}/api/synthetic/seed`, { method: "POST" });
  if (!seedResponse.ok) throw new Error(`Seed failed with ${seedResponse.status}`);
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
    if (response.status() >= 400 && !url.endsWith("/favicon.ico") && !url.endsWith("/api/xero/tenants")) {
      browserErrors.push(`${response.status()} ${url}`);
    }
  });

  try {
    await page.goto(frontendUrl, { waitUntil: "networkidle" });
    await page.getByRole("heading", { name: "Nero" }).waitFor();
    await page.getByText("Northstar Fabrication Works").first().waitFor();
    await page.locator(".recharts-wrapper").waitFor();
    const lineCount = await page.locator(".recharts-line-curve").count();
    if (lineCount < 3) throw new Error(`Expected at least 3 rendered forecast lines, saw ${lineCount}`);
    await expectText(page.locator(".cash-floor-readout"), /£42,000/, "cash floor readout");
    await page.getByText("Recent activity").waitFor();

    const dashboardText = await page.locator("body").innerText();
    if (/Mark paid|Action Log|Open exposure|Variance|Seed portfolio/.test(dashboardText)) {
      throw new Error(`Demo-only or jargon text leaked onto dashboard:\n${dashboardText}`);
    }

    await page.getByRole("button", { name: "Payers" }).click();
    await page.getByRole("heading", { name: "Payment performance" }).waitFor();
    await page.getByPlaceholder("Search customers...").fill("copper");
    await page.getByText("Copperline Manufacturing").first().waitFor();
    await page.getByText("Copperline Manufacturing").first().click();
    await expectText(
      page.locator(".payer-summary"),
      /Based on \d+ paid invoices, Copperline Manufacturing pays on average \d+ days late/,
      "payer timing sentence"
    );
    const payerText = await page.locator("body").innerText();
    if (/Variance|Open exposure|Average days late/.test(payerText)) {
      throw new Error(`Payer jargon leaked into UI:\n${payerText}`);
    }

    await page.getByRole("button", { name: "Agent Queue" }).click();
    await page.getByRole("heading", { name: "Agent Queue" }).waitFor();
    await page.getByRole("button", { name: "Approve" }).first().click();
    await page.getByRole("button", { name: "Outbox" }).click();
    await page.getByRole("heading", { name: "Outbox" }).waitFor();
    await page.getByText(/Foundry Lane Events|Juniper Borough Services|Alder House Retail|Canal House Workspace/).first().waitFor();

    await page.getByRole("button", { name: "Guide" }).click();
    await page.getByRole("heading", { name: "How to use Nero" }).waitFor();
    await page.getByText("Review and approve; nothing is sent without your OK.").waitFor();
    await page.getByTitle("Close").click();

    await page.getByRole("button", { name: "Help & Support" }).click();
    await page.getByRole("heading", { name: "Help & Support" }).waitFor();
    await page.getByText("support@placeholder-domain.com").waitFor();
    await page.getByTitle("Close").click();

    await page.getByRole("button", { name: "Activity" }).click();
    await page.getByRole("heading", { name: "Activity" }).waitFor();
    await page.getByText(/Approved|Loaded Northstar/).first().waitFor();

    await page.keyboard.press("Control+Shift+D");
    await page.getByRole("heading", { name: "Developer tools" }).waitFor();
    await page.getByRole("button", { name: /Seed portfolio/ }).first().waitFor();

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
