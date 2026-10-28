import type { Page } from "@playwright/test";

/**
 * Open a bundled example from the home screen, expanding its gallery group
 * first (only the first group starts open).
 *
 * @param page The page showing the home screen.
 * @param id The example's id, such as "thread-pool".
 */
export async function openSample(page: Page, id: string) {
  const group = page.locator("details").filter({
    has: page.getByTestId(`sample-${id}`),
  });
  if (!(await group.evaluate((el: HTMLDetailsElement) => el.open))) {
    await group.locator("summary").click();
  }
  await page.getByTestId(`open-${id}`).click();
}
