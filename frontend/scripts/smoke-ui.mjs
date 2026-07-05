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

  const connectedReturnPage = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  await connectedReturnPage.goto(`${frontendUrl}/?xero=connected`, { waitUntil: "networkidle" });
  await connectedReturnPage.getByText("Xero connected. Click Sync Xero to pull the latest records.").waitFor();
  if (new URL(connectedReturnPage.url()).searchParams.has("xero")) {
    throw new Error(`OAuth return query was not cleared: ${connectedReturnPage.url()}`);
  }
  await connectedReturnPage.close();

  const connectedButUnsyncedPage = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  await connectedButUnsyncedPage.route("**/api/xero/status", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        connected: true,
        expired: false,
        needs_tenant: false,
        tenant_id: "demo-tenant",
        demo_mode: false,
        client_credentials_configured: true
      })
    })
  );
  await connectedButUnsyncedPage.route("**/api/xero/tenants", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        active_tenant_id: "demo-tenant",
        tenants: [
          { tenant_id: "demo-tenant", tenant_name: "Demo Coffee Ltd", is_active: true }
        ]
      })
    })
  );
  await connectedButUnsyncedPage.route("**/api/data_source", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        mode: "synthetic",
        label: "Northstar Fabrication Works",
        detail: "Local synthetic portfolio.",
        generated_at: "2026-07-05T03:00:00+00:00"
      })
    })
  );
  await connectedButUnsyncedPage.goto(frontendUrl, { waitUntil: "networkidle" });
  await connectedButUnsyncedPage.getByText("Xero is connected. Sync Xero to replace this dashboard with live accounting data.").waitFor();
  await connectedButUnsyncedPage.getByText("Sync Xero").first().waitFor();
  if (await connectedButUnsyncedPage.getByText("Xero connected").count()) {
    throw new Error("Unsynced local dashboard appeared to be live Xero data");
  }
  await connectedButUnsyncedPage.close();

  const erroredReturnPage = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  await erroredReturnPage.goto(
    `${frontendUrl}/?xero=error&message=${encodeURIComponent("Xero connection was cancelled. Try Connect Xero again when ready.")}`,
    { waitUntil: "networkidle" }
  );
  await erroredReturnPage.getByText("Xero connection was cancelled. Try Connect Xero again when ready.").waitFor();
  const erroredUrl = new URL(erroredReturnPage.url());
  if (erroredUrl.searchParams.has("xero") || erroredUrl.searchParams.has("message")) {
    throw new Error(`OAuth error query was not cleared: ${erroredReturnPage.url()}`);
  }
  await erroredReturnPage.close();

  const reconnectPage = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  const reconnectTenantRequests = [];
  reconnectPage.on("request", (request) => {
    if (request.url().endsWith("/api/xero/tenants")) reconnectTenantRequests.push(request.url());
  });
  await reconnectPage.route("**/api/xero/status", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        connected: true,
        expired: true,
        needs_tenant: false,
        demo_mode: false,
        client_credentials_configured: true,
        refresh_error: "Xero token refresh failed. Reconnect Xero to continue syncing."
      })
    })
  );
  await reconnectPage.route("**/api/data_source", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        mode: "xero",
        label: "Xero: Demo Coffee Ltd",
        detail: "Synced from the selected Xero organisation.",
        generated_at: "2026-07-05T03:00:00+00:00",
        tenant_id: "demo-tenant"
      })
    })
  );
  await reconnectPage.goto(frontendUrl, { waitUntil: "networkidle" });
  const reconnectLink = reconnectPage.getByRole("link", { name: "Reconnect Xero" }).first();
  await reconnectLink.waitFor();
  await reconnectPage.getByRole("button", { name: "Disconnect" }).first().waitFor();
  const reconnectHref = await reconnectLink.getAttribute("href");
  if (reconnectHref !== `${backendUrl}/auth/login`) throw new Error(`Reconnect Xero link pointed to ${reconnectHref}`);
  if (await reconnectPage.getByText("Xero Connected").count()) {
    throw new Error("Xero connected badge showed while token refresh required reconnect");
  }
  if (reconnectTenantRequests.length) {
    throw new Error(`Reconnect state still requested Xero tenants:\n${reconnectTenantRequests.join("\n")}`);
  }
  const reconnectFindActions = reconnectPage.getByRole("button", { name: "Find actions" });
  await reconnectFindActions.waitFor();
  if (!(await reconnectFindActions.isDisabled())) {
    throw new Error("Find actions stayed enabled while Xero needed reconnect");
  }
  await reconnectPage.getByRole("button", { name: "Actions", exact: true }).click();
  await reconnectPage.getByRole("heading", { name: "Actions to review" }).waitFor();
  await reconnectPage.getByText("Reconnect Xero before changing actions for this organisation.").waitFor();
  const reconnectApproveButton = reconnectPage.getByRole("button", { name: /Approve/ }).first();
  await reconnectApproveButton.waitFor();
  if (!(await reconnectApproveButton.isDisabled())) {
    throw new Error("Approval stayed enabled while Xero needed reconnect");
  }
  const reconnectSaveWording = reconnectPage.getByRole("button", { name: "Save wording" }).first();
  await reconnectSaveWording.waitFor();
  if (!(await reconnectSaveWording.isDisabled())) {
    throw new Error("Save wording stayed enabled while Xero needed reconnect");
  }
  await reconnectPage.locator(".proposal-card").first().locator("summary").click();
  const reconnectTextarea = reconnectPage.locator(".proposal-card textarea").first();
  await reconnectTextarea.waitFor();
  if (!(await reconnectTextarea.evaluate((node) => node.readOnly))) {
    throw new Error("Draft textarea stayed editable while Xero needed reconnect");
  }
  if ((await reconnectTextarea.evaluate((node) => getComputedStyle(node).cursor)) !== "default") {
    throw new Error("Read-only reconnect draft did not show a locked cursor");
  }
  const reconnectDismiss = reconnectPage.locator(".danger-icon").first();
  await reconnectDismiss.waitFor();
  if (!(await reconnectDismiss.isDisabled())) {
    throw new Error("Dismiss stayed enabled while Xero needed reconnect");
  }
  await reconnectPage.close();

  const needsTenantPage = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  await needsTenantPage.route("**/api/xero/status", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        connected: true,
        expired: false,
        needs_tenant: true,
        tenant_id: null,
        demo_mode: false,
        client_credentials_configured: true
      })
    })
  );
  await needsTenantPage.route("**/api/xero/tenants", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        active_tenant_id: null,
        tenants: [
          { tenant_id: "demo-tenant", tenant_name: "Demo Coffee Ltd", is_active: false }
        ]
      })
    })
  );
  await needsTenantPage.route("**/api/data_source", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        mode: "xero",
        label: "Xero: Demo Coffee Ltd",
        detail: "Synced from the selected Xero organisation.",
        generated_at: "2026-07-05T03:00:00+00:00",
        tenant_id: "demo-tenant"
      })
    })
  );
  await needsTenantPage.goto(frontendUrl, { waitUntil: "networkidle" });
  await needsTenantPage.getByLabel("Xero organisation").waitFor();
  const tenantBlockedFindActions = needsTenantPage.getByRole("button", { name: "Find actions" });
  await tenantBlockedFindActions.waitFor();
  if (!(await tenantBlockedFindActions.isDisabled())) {
    throw new Error("Find actions stayed enabled before a Xero organisation was selected");
  }
  await needsTenantPage.getByRole("button", { name: "Actions", exact: true }).click();
  await needsTenantPage.getByRole("heading", { name: "Actions to review" }).waitFor();
  await needsTenantPage.getByText("Select a Xero organisation before changing actions.").waitFor();
  await needsTenantPage.close();

  const tenantMismatchPage = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  await tenantMismatchPage.route("**/api/xero/status", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        connected: true,
        expired: false,
        needs_tenant: false,
        demo_mode: false,
        tenant_id: "new-tenant",
        client_credentials_configured: true
      })
    })
  );
  await tenantMismatchPage.route("**/api/xero/tenants", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        active_tenant_id: "new-tenant",
        tenants: [
          { tenant_id: "old-tenant", tenant_name: "Old Coffee Ltd", is_active: false },
          { tenant_id: "new-tenant", tenant_name: "New Coffee Ltd", is_active: true }
        ]
      })
    })
  );
  await tenantMismatchPage.route("**/api/data_source", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        mode: "xero",
        label: "Xero: Old Coffee Ltd",
        detail: "Synced from the selected Xero organisation.",
        generated_at: "2026-07-05T03:00:00+00:00",
        tenant_id: "old-tenant"
      })
    })
  );
  await tenantMismatchPage.goto(frontendUrl, { waitUntil: "networkidle" });
  await tenantMismatchPage.getByText("Sync needed").waitFor();
  await tenantMismatchPage.getByRole("button", { name: "Disconnect" }).first().waitFor();
  await tenantMismatchPage.getByText("Xero organisation changed. Sync Xero to update this dashboard before reviewing actions.").waitFor();
  const staleFindActions = tenantMismatchPage.getByRole("button", { name: "Find actions" });
  await staleFindActions.waitFor();
  if (!(await staleFindActions.isDisabled())) {
    throw new Error("Find actions stayed enabled while the Xero dashboard needed a sync");
  }
  await tenantMismatchPage.getByRole("button", { name: "Actions", exact: true }).click();
  await tenantMismatchPage.getByRole("heading", { name: "Actions to review" }).waitFor();
  await tenantMismatchPage.getByText("Sync Xero before changing actions for this organisation.").waitFor();
  const staleApproveButton = tenantMismatchPage.getByRole("button", { name: /Approve/ }).first();
  await staleApproveButton.waitFor();
  if (!(await staleApproveButton.isDisabled())) {
    throw new Error("Approval stayed enabled while the Xero dashboard needed a sync");
  }
  const staleSaveWording = tenantMismatchPage.getByRole("button", { name: "Save wording" }).first();
  await staleSaveWording.waitFor();
  if (!(await staleSaveWording.isDisabled())) {
    throw new Error("Save wording stayed enabled while the Xero dashboard needed a sync");
  }
  await tenantMismatchPage.locator(".proposal-card").first().locator("summary").click();
  const staleTextarea = tenantMismatchPage.locator(".proposal-card textarea").first();
  await staleTextarea.waitFor();
  if (!(await staleTextarea.evaluate((node) => node.readOnly))) {
    throw new Error("Draft textarea stayed editable while the Xero dashboard needed a sync");
  }
  if ((await staleTextarea.evaluate((node) => getComputedStyle(node).cursor)) !== "default") {
    throw new Error("Read-only stale draft did not show a locked cursor");
  }
  const staleDismiss = tenantMismatchPage.locator(".danger-icon").first();
  await staleDismiss.waitFor();
  if (!(await staleDismiss.isDisabled())) {
    throw new Error("Dismiss stayed enabled while the Xero dashboard needed a sync");
  }
  await tenantMismatchPage.close();

  const staleOutboxPage = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  await staleOutboxPage.route("**/api/outbox", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([
        {
          id: "stale-outbox-1",
          timestamp: "2026-07-05T03:00:00+00:00",
          to: "Demo Retail",
          to_email: "accounts@demoretail.example.com",
          subject: "Reminder: PAID-1",
          body: "Please pay PAID-1.",
          invoice_id: "paid-1",
          proposal_id: "proposal-paid-1",
          status: "stale",
          send_disabled_reason: "This invoice is no longer open in Xero."
        }
      ])
    })
  );
  await staleOutboxPage.goto(frontendUrl, { waitUntil: "networkidle" });
  await staleOutboxPage.getByRole("button", { name: "Outbox" }).click();
  await staleOutboxPage.getByRole("heading", { name: "Outbox" }).waitFor();
  await staleOutboxPage.getByText("Closed in Xero").waitFor();
  if (await staleOutboxPage.getByRole("link", { name: "Open draft" }).count()) {
    throw new Error("Closed Xero invoice still exposed a sendable outbox draft");
  }
  const staleCopyButton = staleOutboxPage.getByRole("button", { name: "Copy" }).first();
  await staleCopyButton.waitFor();
  if (!(await staleCopyButton.isDisabled())) {
    throw new Error("Closed Xero invoice outbox draft could still be copied");
  }
  await staleOutboxPage.close();

  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  const browserErrors = [];
  const initialReadPreflights = [];
  let trackInitialReads = true;
  page.on("request", (request) => {
    if (trackInitialReads && request.method() === "OPTIONS") initialReadPreflights.push(request.url());
  });
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
    trackInitialReads = false;
    if (initialReadPreflights.length) {
      throw new Error(`Initial dashboard reads triggered avoidable CORS preflights:\n${initialReadPreflights.join("\n")}`);
    }
    await page.getByText("Northstar Fabrication Works").first().waitFor();
    await page.getByText(/^Updated /).first().waitFor();
    await page.getByText("Due now or soon").waitFor();
    await page.getByText("Likely by then").waitFor();
    await page.getByText("Ready to bring forward").waitFor();
    await page.getByRole("button", { name: "Find actions" }).waitFor();
    await page.getByText("Minimum cash").first().waitFor();
    await page.getByText("Likely payment date").waitFor();
    await page.getByText("After approved actions").waitFor();
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
    if (/Mark paid|Action Log|Open exposure|Variance|Seed portfolio|proposal\(s\)|profile\(s\)|Materialised|Agent run complete|Run agent|Cash floor|Forecast floor|Predicted \(Nero\)|Due envelope/.test(dashboardText)) {
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
    const statementLink = page.getByRole("link", { name: "Open statement" });
    await statementLink.waitFor();
    const statementHref = await statementLink.getAttribute("href");
    if (!statementHref?.startsWith(`${backendUrl}/api/statements/`)) {
      throw new Error(`Statement link pointed to ${statementHref}`);
    }
    const [statementPage] = await Promise.all([
      page.context().waitForEvent("page"),
      statementLink.click()
    ]);
    await statementPage.getByText("Customer statement").waitFor();
    await statementPage.getByText("Copperline Manufacturing").waitFor();
    await statementPage.getByText("Print or save as PDF").waitFor();
    await statementPage.close();
    await page.getByPlaceholder("Search customers...").fill("kite");
    await page.getByText("Kite & Kettle Cafes").first().waitFor();
    await page.getByText("Kite & Kettle Cafes").first().click();
    await expectText(
      page.locator(".payer-summary"),
      /Kite & Kettle Cafes pays on average \d+ days early/,
      "early payer timing sentence"
    );
    const payerText = await page.locator("body").innerText();
    if (/Variance|Open exposure|Average days late|Low Data|Grade/.test(payerText)) {
      throw new Error(`Payer jargon leaked into UI:\n${payerText}`);
    }

    await page.getByRole("button", { name: "Actions" }).click();
    await page.getByRole("heading", { name: "Actions to review" }).waitFor();
    await page.getByText(/Send reminder|Send firmer reminder|Ask for deposit|Change payment terms/).first().waitFor();
    const actionCards = await page.locator(".proposal-card").evaluateAll((cards) =>
      cards.map((card) => ({
        priority: Number(card.getAttribute("data-priority") || "0"),
        impact: Number((card.querySelector(".impact")?.textContent || "").match(/£([\d,]+)/)?.[1]?.replace(/,/g, "") || "0"),
        text: card.textContent || ""
      }))
    );
    for (let index = 1; index < actionCards.length; index += 1) {
      const previous = actionCards[index - 1];
      const current = actionCards[index];
      if (current.priority < previous.priority) {
        throw new Error(`Action cards were not sorted by actionability: ${JSON.stringify(actionCards, null, 2)}`);
      }
      if (current.priority === previous.priority && current.impact > previous.impact) {
        throw new Error(`Action cards were not sorted by cash impact within an actionability group: ${JSON.stringify(actionCards, null, 2)}`);
      }
    }
    await page.getByText(/Could bring £[\d,]+ forward about \d+ days? sooner\./).first().waitFor();
    await page.getByText("Approve to keep the draft in Outbox. Nothing is sent automatically.").first().waitFor();
    const actionsText = await page.locator("body").innerText();
    if (/across 0 paid invoices|deposit_recommendation|terms_recommendation|I have\s+attached|\{payment_link\}/.test(actionsText)) {
      throw new Error(`Internal action copy leaked into UI:\n${actionsText}`);
    }
    const editMarker = "Please reply today so we can keep stock orders moving.";
    const firstDraftCard = page.locator(".proposal-card").filter({
      has: page.getByRole("button", { name: "Approve draft" })
    }).first();
    await firstDraftCard.locator("summary").click();
    const draftTextarea = firstDraftCard.locator("textarea");
    await draftTextarea.fill(`${await draftTextarea.inputValue()}\n\n${editMarker}`);
    await firstDraftCard.getByRole("button", { name: "Approve draft" }).click();
    await page.getByRole("button", { name: "Outbox" }).click();
    await page.getByRole("heading", { name: "Outbox" }).waitFor();
    await page.getByText(/Foundry Lane Events|Juniper Borough Services|Alder House Retail|Canal House Workspace/).first().waitFor();
    await page.locator(".message-preview").first().locator("summary").click();
    await page.getByText(editMarker).waitFor();
    await expectText(page.locator(".recipient-email").first(), /^accounts@.+\.example\.com$/i, "outbox recipient email");
    await page.getByRole("button", { name: "Copy" }).first().waitFor();
    const outboxDraftLink = page.getByRole("link", { name: "Open draft" }).first();
    await outboxDraftLink.waitFor();
    const outboxDraftHref = await outboxDraftLink.getAttribute("href");
    if (!outboxDraftHref?.startsWith("mailto:") || outboxDraftHref.startsWith("mailto:?") || !outboxDraftHref.includes("?subject=")) {
      throw new Error(`Outbox draft link did not open an addressed mail draft: ${outboxDraftHref}`);
    }
    if (outboxDraftHref.includes("%7Bpayment_link%7D")) {
      throw new Error(`Outbox draft leaked a payment-link placeholder: ${outboxDraftHref}`);
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

    const mobilePage = await browser.newPage({ viewport: { width: 390, height: 844 }, isMobile: true });
    await mobilePage.goto(frontendUrl, { waitUntil: "networkidle" });
    await mobilePage.getByRole("heading", { name: "Nero" }).waitFor();
    await mobilePage.locator(".mobile-invoice-list").waitFor();
    if (!(await mobilePage.locator(".mobile-invoice-card").first().isVisible())) {
      throw new Error("Mobile invoice cards were not visible at phone width");
    }
    await mobilePage.close();

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
