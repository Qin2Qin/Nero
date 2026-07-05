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
  const errorPage = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  await errorPage.route("**/api/forecast", (route) =>
    route.fulfill({
      status: 502,
      contentType: "application/json",
      body: JSON.stringify({ detail: "Forecast temporarily unavailable" })
    })
  );
  await errorPage.goto(frontendUrl, { waitUntil: "networkidle" });
  await errorPage.getByText("Forecast temporarily unavailable").waitFor();
  await errorPage.close();

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
    await page.getByText(/^Updated /).first().waitFor();
    await page.getByText("Due now or soon").waitFor();
    await page.getByText("Likely by then").waitFor();
    await page.getByText("Late invoices by age").waitFor();
    await page.getByText("1-30 days late").waitFor();
    await page.getByText(/\d+ days overdue/).first().waitFor();
    await page.getByRole("button", { name: "Review action" }).first().click();
    await page.getByRole("heading", { name: "Actions to review" }).waitFor();
    await page.getByRole("button", { name: "Dashboard" }).click();
    await page.getByRole("heading", { name: "Nero" }).waitFor();
    await page.locator(".recharts-wrapper").waitFor();
    const lineCount = await page.locator(".recharts-line-curve").count();
    if (lineCount < 3) throw new Error(`Expected at least 3 rendered forecast lines, saw ${lineCount}`);
    await expectText(page.locator(".cash-floor-readout"), /£42,000/, "cash floor readout");
    await page.getByText(/Connect Xero|Sync Xero|Xero setup needed/).first().waitFor();
    const connectXeroLink = page.getByRole("link", { name: "Connect Xero" });
    if ((await connectXeroLink.count()) > 0) {
      const href = await connectXeroLink.first().getAttribute("href");
      if (href !== `${backendUrl}/auth/login`) throw new Error(`Connect Xero link pointed to ${href}`);
    }
    await page.getByText("Recent activity").waitFor();
    await page.getByText(/suggested actions? ready for your review/i).first().waitFor();

    const dashboardText = await page.locator("body").innerText();
    if (/Mark paid|Action Log|Open exposure|Variance|Seed portfolio|proposal\(s\)|profile\(s\)|Materialised|Agent run complete/.test(dashboardText)) {
      throw new Error(`Demo-only or jargon text leaked onto dashboard:\n${dashboardText}`);
    }
    await expectText(
      page.locator(".roi-strip"),
      /Review \d+ suggested actions to bring £[\d,]+ forward about \d+ days sooner\. Nothing is sent without your OK\./,
      "pending cash summary"
    );
    await page.getByRole("button", { name: /Review actions/ }).click();
    await page.getByRole("heading", { name: "Actions to review" }).waitFor();
    await page.getByRole("button", { name: "Dashboard" }).click();
    await page.getByRole("heading", { name: "Nero" }).waitFor();

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
    await page.getByPlaceholder("Search customers...").fill("kite");
    await page.getByText("Kite & Kettle Cafes").first().waitFor();
    await page.getByText("Kite & Kettle Cafes").first().click();
    await expectText(
      page.locator(".payer-summary"),
      /Kite & Kettle Cafes pays on average \d+ days early/,
      "early payer timing sentence"
    );
    const payerText = await page.locator("body").innerText();
    if (/Variance|Open exposure|Average days late/.test(payerText)) {
      throw new Error(`Payer jargon leaked into UI:\n${payerText}`);
    }

    await page.getByRole("button", { name: "Actions" }).click();
    await page.getByRole("heading", { name: "Actions to review" }).waitFor();
    await page.getByText(/Send reminder|Send firmer reminder|Ask for deposit|Change payment terms/).first().waitFor();
    await page.getByText(/Could bring £[\d,]+ forward about \d+ days? sooner\./).first().waitFor();
    const actionsText = await page.locator("body").innerText();
    if (/across 0 paid invoices|deposit_recommendation|terms_recommendation/.test(actionsText)) {
      throw new Error(`Internal action copy leaked into UI:\n${actionsText}`);
    }
    await page.getByRole("button", { name: /Approve/ }).first().click();
    await page.getByRole("button", { name: "Outbox" }).click();
    await page.getByRole("heading", { name: "Outbox" }).waitFor();
    await page.getByText(/Foundry Lane Events|Juniper Borough Services|Alder House Retail|Canal House Workspace/).first().waitFor();
    const outboxDraftLink = page.getByRole("link", { name: "Open draft" }).first();
    await outboxDraftLink.waitFor();
    const outboxDraftHref = await outboxDraftLink.getAttribute("href");
    if (!outboxDraftHref?.startsWith("mailto:?subject=")) {
      throw new Error(`Outbox draft link did not open a mail draft: ${outboxDraftHref}`);
    }

    await page.getByRole("button", { name: "Guide" }).click();
    await page.getByRole("heading", { name: "How to use Nero" }).waitFor();
    await page.getByText("Review and approve; nothing is sent without your OK.").waitFor();
    await page.getByText("Open Actions to review suggested reminders or smarter payment terms.").waitFor();
    await page.getByTitle("Close").click();

    await page.getByRole("button", { name: "Help & Support" }).click();
    await page.getByRole("heading", { name: "Help & Support" }).waitFor();
    await page.getByText("support@nero.cash").waitFor();
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
