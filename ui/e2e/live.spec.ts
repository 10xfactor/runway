import { expect, test } from "@playwright/test";

// Requires: `RUNWAY_TOKEN=devtoken runway dev --no-open` running against an empty store.
const TOKEN = process.env.RUNWAY_TOKEN ?? "devtoken";
const shot = (name: string) => `../reports/ui/${name}.png`;

test("live demo: repair then pass, inspect, replay", async ({ page }) => {
  const external: string[] = [];
  page.on("request", (r) => { if (!/^(http:\/\/127\.0\.0\.1|data:|blob:)/.test(r.url())) external.push(r.url()); });

  await page.goto(`/#token=${TOKEN}`);
  await expect(page.getByRole("heading", { name: "Runs" })).toBeVisible();
  await page.screenshot({ path: shot("01-runs-empty") });

  await page.getByRole("button", { name: /Run (the )?offline demo/ }).first().click();
  await expect(page).toHaveURL(/\/runs\/run_/);
  await page.waitForTimeout(2500);
  await page.screenshot({ path: shot("02-live-midrun") });

  await expect(page.getByText("SUCCEEDED")).toBeVisible({ timeout: 40_000 });
  await page.screenshot({ path: shot("03-complete") });

  await page.getByRole("button", { name: /architect: Committed/ }).click();
  await page.getByRole("tab", { name: /Repair Lens/ }).click();
  await expect(page.getByText("Feedback injected into attempt 2")).toBeVisible();
  await page.screenshot({ path: shot("04-repair-lens") });

  await page.keyboard.press("r");
  await expect(page.getByText("Replay Studio")).toBeVisible();
  await page.waitForTimeout(500);
  await page.screenshot({ path: shot("05-replay-studio") });

  expect(external, "Console must make no non-loopback requests").toEqual([]);
});
