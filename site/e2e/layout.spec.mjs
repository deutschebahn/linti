import { test, expect } from '@playwright/test'

const widths = [390, 820, 1024, 1280]

for (const width of widths) {
  test(`tool pages fit ${width}px without horizontal scrolling`, async ({ browser }) => {
    const page = await browser.newPage({ viewport: { width, height: 900 } })
    for (const path of ['/linti/playground', '/linti/rules', '/linti/config']) {
      await page.goto(path)
      await page.locator('.lint-tool').waitFor()
      expect(await page.evaluate(() => document.documentElement.scrollWidth), path).toBeLessThanOrEqual(width)
    }
    // Next to Docus' navigation the form must stay usable, or stack.
    const form = await page.locator('.form-pane').boundingBox()
    expect(form.width).toBeGreaterThanOrEqual(320)
    await page.close()
  })
}

test('sticky panels stay below the site header', async ({ browser }) => {
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } })
  for (const [path, selector] of [['/linti/rules', '.reference-sidebar'], ['/linti/config', '.yaml-pane'], ['/linti/playground', '.results']]) {
    await page.goto(path)
    await page.locator(selector).waitFor()
    // Scroll within the panel's section, not past its end.
    await page.mouse.wheel(0, 500)
    await page.waitForTimeout(300)
    const header = await page.locator('header').first().boundingBox()
    const panel = await page.locator(selector).boundingBox()
    expect(panel.y, selector).toBeGreaterThanOrEqual(header.y + header.height)
  }
  await page.close()
})

test('editors use 16px text on phones so iOS does not zoom', async ({ browser }) => {
  const page = await browser.newPage({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true })
  await page.goto('/linti/playground')
  await page.locator('.cm-content').waitFor()
  expect(await page.locator('.cm-content').evaluate(node => getComputedStyle(node).fontSize)).toBe('16px')
  await page.close()
})

test('the configurator keeps saving within reach on phones', async ({ browser }) => {
  const page = await browser.newPage({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true })
  await page.goto('/linti/config')
  await page.locator('.configurator .cm-editor').waitFor({ state: 'attached' })
  await page.locator('#rule-keyword_casing').getByRole('switch', { name: /^Enable / }).click()
  const bar = page.locator('.save-bar')
  await expect(bar).toBeVisible()
  await page.mouse.wheel(0, 3000)
  await page.waitForTimeout(300)
  const box = await bar.boundingBox()
  expect(box.y + box.height).toBeLessThanOrEqual(844 + 1)
  await page.close()
})
