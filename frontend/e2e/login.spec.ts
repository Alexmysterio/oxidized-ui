import { expect, test } from "@playwright/test";
const meta = { setup_required: false, oidc_enabled: false, available_languages: ["es", "en"], default_language: "es", app_version: "test", timezone: "Europe/Madrid" };
test("login page renders", async ({ page }) => {
  await page.route("**/api/meta", (route) => route.fulfill({ json: meta }));
  await page.route("**/api/auth/session", (route) => route.fulfill({ status: 401, json: { error: { code: "auth.unauthenticated", params: {} } } }));
  await page.goto("/login");
  await expect(page).toHaveTitle("Oxidized UI");
  await expect(page).toHaveURL(/\/login/);
  await expect(page.locator("#username")).toHaveAttribute("placeholder", /^(Usuario|Username)$/);
});
