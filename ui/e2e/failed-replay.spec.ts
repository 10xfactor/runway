import { expect, test } from "@playwright/test";

const TOKEN = process.env.RUNWAY_TOKEN ?? "devtoken";
const shot = (name: string) => `../reports/ui/${name}.png`;

test("failed task: replay from it reuses upstream and succeeds", async ({ page }) => {
  await page.goto(`/#token=${TOKEN}`);
  await page.getByRole("button", { name: /failing task/ }).first().click();
  await expect(page).toHaveURL(/\/runs\/run_/);
  await expect(page.getByText("run.failed")).toBeVisible({ timeout: 40_000 });
  await page.screenshot({ path: shot("06-failed-run") });

  await page.getByRole("button", { name: "Replay" }).click();
  await expect(page.getByText("Replay Studio")).toBeVisible();
  await expect(page.getByText("REUSE").first()).toBeVisible();
  await page.waitForTimeout(800);
  await page.screenshot({ path: shot("07-replay-from-failed") });

  await page.getByRole("button", { name: "Start replay" }).click();
  await expect(page.getByText("run.completed")).toBeVisible({ timeout: 40_000 });
  await expect(page.getByText("task.cached").first()).toBeVisible();
});

test("command palette lists the open run's tasks", async ({ page }) => {
  await page.goto(`/#token=${TOKEN}`);
  await page.getByRole("link", { name: /run_/ }).first().click();
  await page.keyboard.press("Control+k");
  await expect(page.getByRole("dialog", { name: "Command palette" })).toBeVisible();
  await expect(page.getByText("Inspect task: architect")).toBeVisible();
  await page.screenshot({ path: shot("08-command-palette") });
  await page.keyboard.press("Escape");
  await page.keyboard.press("?");
  await expect(page.getByRole("dialog", { name: "Keyboard shortcuts" })).toBeVisible();
});
