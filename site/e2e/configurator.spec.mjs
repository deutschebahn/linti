import { test, expect } from '@playwright/test'

test('repeated rule/configurator round trips reveal the rule and retain edits', async ({ page }) => {
  page.on('dialog', dialog => dialog.accept())
  await page.goto('/linti/rules?rule=F110')
  await expect(page.getByRole('heading', { name: 'Try F110' })).toBeVisible()

  for (let visit = 0; visit < 3; visit++) {
    await page.getByRole('button', { name: 'Adjust F110 in configurator' }).click()
    await page.waitForURL(url => url.pathname === '/linti/config' && url.searchParams.get('rule') === 'F110')
    await page.locator('.configurator .cm-editor').waitFor({ state: 'attached' })

    const card = page.locator('#rule-keyword_casing')
    await expect(card.locator('details')).toHaveAttribute('open', '')
    // Let Nuxt's navigation scroll and the card's smooth scroll both finish.
    // Checking immediately would miss a later reset to the top of the page.
    await page.waitForTimeout(750)
    const bounds = await card.boundingBox()
    expect(bounds).not.toBeNull()
    expect(bounds.y).toBeGreaterThanOrEqual(0)
    expect(bounds.y).toBeLessThan(page.viewportSize().height - 120)

    const enabled = card.getByRole('switch', { name: /^Enable / })
    await enabled.click()
    await expect(enabled).toHaveAttribute('aria-checked', visit % 2 === 0 ? 'false' : 'true')
    await page.getByRole('link', { name: 'Back to rule F110' }).click()
    await page.waitForURL(url => url.pathname === '/linti/rules' && url.searchParams.get('config') === 'working')
    await expect(page.getByRole('heading', { name: 'Try F110' })).toBeVisible()
    // A later visit must reuse the edited working draft, rather than replacing it.
    if (visit % 2 === 0) {
      await expect(page.locator('.config-inspection pre')).toContainText('enabled: false')
    } else {
      await expect(page.locator('.config-inspection summary')).toContainText('Configuration used:')
    }
  }
})
