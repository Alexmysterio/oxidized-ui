import { expect, test } from "@playwright/test";

const session = {
  user: {
    id: 1,
    username: "admin",
    full_name: "Admin",
    email: null,
    avatar_url: null,
    role: "admin",
    language: "es",
    theme: "system",
    scope_groups: [],
  },
  csrf_token: "test-csrf",
  capabilities: [
    "nodes.read",
    "nodes.write",
    "backups.trigger",
    "versions.read",
    "config.read",
    "config.write",
    "config.apply",
    "groups.write",
    "logs.read",
    "jobs.read",
    "users.manage",
    "audit.read",
    "system.manage",
    "compliance.read",
    "compliance.write",
    "me.write",
  ],
};

const meta = {
  setup_required: false,
  oidc_enabled: false,
  available_languages: ["es", "en"],
  default_language: "es",
  app_version: "test",
  timezone: "Europe/Madrid",
  site_name: "Oxidized UI",
  logo_url: null,
};

const node = {
  id: 1,
  name: "core-1",
  address: "10.0.0.1",
  model: "ios",
  group_name: null,
  status: "ok",
  last_status_raw: "success",
  last_backup_at: new Date().toISOString(),
  last_failure_at: null,
  last_attempt_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
  warnings: [],
  tags: {},
  maintenance: false,
  retry: null,
  config_state: null,
  facts: null,
  input: "ssh",
  port: 22,
  username: "netops",
  has_password: true,
  has_enable: false,
  vars: {},
};

test("sidebar stays usable after node edit and navigation", async ({ page }) => {
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/api/meta")) return route.fulfill({ json: meta });
    if (path.endsWith("/api/auth/session")) return route.fulfill({ json: session });
    if (/\/api\/nodes\/1$/.test(path)) return route.fulfill({ json: node });
    if (path.endsWith("/api/nodes/1/status")) {
      return route.fulfill({
        json: {
          node_id: 1,
          status: "ok",
          last_status_raw: "success",
          last_started_at: new Date().toISOString(),
          last_finished_at: new Date().toISOString(),
          last_success_at: new Date().toISOString(),
          last_failure_at: null,
          observed_at: new Date().toISOString(),
          active_job_id: null,
          stale: false,
        },
      });
    }
    if (path.endsWith("/api/nodes/1/versions")) {
      return route.fulfill({ json: { available: true, reason: null, versions: [] } });
    }
    if (path.endsWith("/api/nodes/1/config")) return route.fulfill({ body: "hostname core-1\n", contentType: "text/plain" });
    if (path.endsWith("/api/groups")) return route.fulfill({ json: { groups: [], requires_admin_apply: false, draft_revision_id: null } });
    if (path.endsWith("/api/config/catalog")) {
      return route.fulfill({
        json: {
          models: ["ios"],
          model_vendors: { ios: "cisco" },
          inputs: ["ssh"],
          outputs: ["git"],
          vars: [],
          prompts: [],
        },
      });
    }
    if (path.endsWith("/api/nodes/tags")) return route.fulfill({ json: { items: [] } });
    if (path.endsWith("/api/preferences")) return route.fulfill({ json: { favorites: [], saved_filters: [] } });
    if (path.endsWith("/api/status")) {
      return route.fulfill({
        json: {
          oxidized: { state: "online", api_online: true, container_state: "running", container_running: true, health: "healthy", last_seen_at: null, version: null },
          nodes: { total: 1, ok: 1, failed: 0, pending: 0, never: 0 },
          backups: { last_success_at: null, last_failure_at: null, active_jobs: 0 },
          activity: [],
          sla: { days: 14, groups: [] },
          warnings: [],
        },
      });
    }
    if (path.endsWith("/api/jobs")) return route.fulfill({ json: { items: [], page: 1, page_size: 25, total: 0, total_pages: 1 } });
    return route.fulfill({ json: {} });
  });

  await page.goto("/nodes/1");
  await expect(page.getByRole("heading", { name: "core-1" })).toBeVisible();

  const nodesLink = page.locator('aside a[href="/nodes"]').first();
  await nodesLink.click();
  await expect(page).toHaveURL(/\/nodes$/);

  await page.goto("/nodes/1");
  await expect(page.getByRole("heading", { name: "core-1" })).toBeVisible();

  await page.getByRole("button", { name: "Editar" }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.getByRole("button", { name: "Cancelar" }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);

  await nodesLink.click();
  await expect(page).toHaveURL(/\/nodes$/);
});

test("mobile drawer stays usable after node navigation and edit", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/api/meta")) return route.fulfill({ json: meta });
    if (path.endsWith("/api/auth/session")) return route.fulfill({ json: session });
    if (/\/api\/nodes\/1$/.test(path)) return route.fulfill({ json: node });
    if (path.endsWith("/api/nodes/1/status")) {
      return route.fulfill({
        json: {
          node_id: 1,
          status: "ok",
          last_status_raw: "success",
          last_started_at: new Date().toISOString(),
          last_finished_at: new Date().toISOString(),
          last_success_at: new Date().toISOString(),
          last_failure_at: null,
          observed_at: new Date().toISOString(),
          active_job_id: null,
          stale: false,
        },
      });
    }
    if (path.endsWith("/api/nodes/1/versions")) {
      return route.fulfill({ json: { available: true, reason: null, versions: [] } });
    }
    if (path.endsWith("/api/nodes/1/config")) return route.fulfill({ body: "hostname core-1\n", contentType: "text/plain" });
    if (path.endsWith("/api/groups")) return route.fulfill({ json: { groups: [], requires_admin_apply: false, draft_revision_id: null } });
    if (path.endsWith("/api/config/catalog")) {
      return route.fulfill({
        json: { models: ["ios"], model_vendors: { ios: "cisco" }, inputs: ["ssh"], outputs: ["git"], vars: [], prompts: [] },
      });
    }
    if (path.endsWith("/api/nodes/tags")) return route.fulfill({ json: { items: [] } });
    if (path.endsWith("/api/preferences")) return route.fulfill({ json: { favorites: [], saved_filters: [] } });
    if (path.endsWith("/api/status")) {
      return route.fulfill({
        json: {
          oxidized: { state: "online", api_online: true, container_state: "running", container_running: true, health: "healthy", last_seen_at: null, version: null },
          nodes: { total: 1, ok: 1, failed: 0, pending: 0, never: 0 },
          backups: { last_success_at: null, last_failure_at: null, active_jobs: 0 },
          activity: [],
          sla: { days: 14, groups: [] },
          warnings: [],
        },
      });
    }
    if (path.endsWith("/api/jobs")) return route.fulfill({ json: { items: [], page: 1, page_size: 25, total: 0, total_pages: 1 } });
    return route.fulfill({ json: {} });
  });

  await page.goto("/nodes/1");
  await expect(page.getByRole("heading", { name: "core-1" })).toBeVisible();

  await page.getByRole("button", { name: "Abrir menú" }).click();
  await page.getByRole("dialog").getByRole("link", { name: "Nodos" }).click();
  await expect(page).toHaveURL(/\/nodes$/);

  await page.getByRole("button", { name: "Abrir menú" }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);

  await page.goto("/nodes/1");
  await page.getByRole("button", { name: "Editar" }).click();
  await page.getByRole("button", { name: "Cancelar" }).click();
  await page.getByRole("button", { name: "Abrir menú" }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
});

