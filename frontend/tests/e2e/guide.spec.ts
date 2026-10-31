import AxeBuilder from "@axe-core/playwright";
import { appendFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { expect, test, type Page } from "@playwright/test";

// Master prompt §11: the whole guide for two profiles on desktop, Android and iPhone, with axe.

async function expectNoSeriousA11yIssues(page: Page, where: string) {
  const result = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
    // The map canvas is decorative and the list next to it is its text equivalent. Markers can
    // overlap when spaces share a building; WCAG 2.5.8 allows that because every marker has an
    // equivalent "Detalj" link in the list, which is checked here with everything else.
    .exclude(".maplibregl-canvas")
    .exclude(".maplibregl-marker")
    .analyze();
  const serious = result.violations.filter(
    (v) => v.impact === "serious" || v.impact === "critical",
  );
  // Full node list for whoever fixes it; the assertion message stays short.
  const lines = serious.flatMap((v) => v.nodes.map((n) => `${where} ${v.id} ${n.html}`));
  if (lines.length) appendFileSync(join(tmpdir(), "prostoriq-axe.txt"), lines.join("\n") + "\n");
  expect(
    serious.map((v) => `${where}: ${v.id} (${v.nodes.length}) ${v.help}`),
    `axe: ${where}`,
  ).toEqual([]);
}

/** Runs the guide with default settings and returns the order of the first results. */
async function runGuide(page: Page, profileName: string): Promise<string[]> {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Što planirate otvoriti?" })).toBeVisible();
  await page.getByText(profileName, { exact: true }).click();
  await page.getByRole("button", { name: "Dalje" }).click();
  await expect(page.getByRole("heading", { name: "Kakav prostor tražite?" })).toBeVisible();
  await page.getByRole("button", { name: "Dalje" }).click();
  await expect(page.getByRole("heading", { name: "Što vam je važno?" })).toBeVisible();
  await page.getByRole("button", { name: "Prikaži rezultate" }).click();

  const results = page.getByRole("heading", { name: /^Rangirano \d+ od \d+ prostora$/ });
  const dialog = page.getByRole("dialog");
  await expect(results.or(dialog)).toBeVisible();
  if (await dialog.isVisible()) {
    // 409: nothing is preselected, the user must choose (ADR03).
    await expect(dialog.getByRole("button", { name: "Potvrdi i izračunaj" })).toBeDisabled();
    await dialog.getByRole("radio", { name: /^Usporedi svih/ }).check();
    await dialog.getByRole("button", { name: "Potvrdi i izračunaj" }).click();
  }
  await expect(results).toBeVisible();
  await expect(page.getByText(/Popis Grada iz 2024/).first()).toBeVisible();

  const links = page.getByRole("link", { name: /^Detalj: / });
  await expect(links.first()).toBeVisible();
  const labels = await links.evaluateAll((els) =>
    els.slice(0, 8).map((el) => el.getAttribute("aria-label") ?? ""),
  );
  return labels;
}

test("café and office give different orders, and the pages pass axe", async ({ page }) => {
  const limited: string[] = [];
  page.on("response", (r) => {
    if (r.status() === 429) limited.push(r.url());
  });

  const cafe = await runGuide(page, "Kafić / bar");
  await expectNoSeriousA11yIssues(page, "rezultati kafić");
  const office = await runGuide(page, "Ured");
  expect(office.length).toBeGreaterThan(3);
  expect(office).not.toEqual(cafe);

  // A normal visit must never hit the rate limit.
  expect(limited).toEqual([]);
});

test("detail shows evidence, competition and what is unknown", async ({ page }) => {
  await runGuide(page, "Kafić / bar");
  await page
    .getByRole("link", { name: /^Detalj: / })
    .first()
    .click();
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await expect(
    page.getByText("Evidentirani objekti u OSM-u; popis možda nije potpun").first(),
  ).toBeVisible();
  await expect(page.getByText(/zračno/i).first()).toBeVisible();
  await expectNoSeriousA11yIssues(page, "detalj");
});

test("compare allows at most three spaces", async ({ page }) => {
  await runGuide(page, "Kafić / bar");
  const boxes = page.getByRole("checkbox", { name: "Usporedi" });
  for (let i = 0; i < 3; i++) await boxes.nth(i).check();
  await expect(boxes.nth(3)).toBeDisabled();
  await page.getByRole("button", { name: /Usporedi \(3\/3\)/ }).click();
  await expect(page).toHaveURL(/\/usporedba/);
  await expectNoSeriousA11yIssues(page, "usporedba");
});

test("profile suggestion proposes, the user chooses", async ({ page }) => {
  await page.goto("/");
  await page
    .getByLabel("Opišite djelatnost")
    .fill("Otvaram mali kafić s kavom i kolačima za studente");
  await page.getByRole("button", { name: "Predloži djelatnost" }).click();
  await expect(page.getByRole("button", { name: /Odaberi/ }).first()).toBeVisible();
  await expectNoSeriousA11yIssues(page, "prijedlog djelatnosti");
});

test("sources page lists licences and the start page passes axe", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Što planirate otvoriti?" })).toBeVisible();
  await expectNoSeriousA11yIssues(page, "početna");
  await page.goto("/izvori");
  await expect(page.getByText(/ODbL/).first()).toBeVisible();
  await expectNoSeriousA11yIssues(page, "izvori");
});
