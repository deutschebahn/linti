import { readdir, readFile } from 'node:fs/promises'
import { test, expect } from '@playwright/test'

const LIBRARY_KEY = 'linti:config-library:v1'
const PUBLIC = new URL('../.output/public/', import.meta.url)

function shareHash(name, yaml) {
  return `#config=v1.${Buffer.from(JSON.stringify({ name, yaml })).toString('base64url')}`
}

async function storedNames(page) {
  return page.evaluate(key => JSON.parse(localStorage.getItem(key) || '{"profiles":[]}').profiles.map(profile => profile.name), LIBRARY_KEY)
}

test('a second open tab keeps profiles saved in the first', async ({ context }) => {
  const tabA = await context.newPage()
  const tabB = await context.newPage()
  for (const tab of [tabA, tabB]) tab.on('dialog', dialog => dialog.accept())
  await tabB.goto('/linti/rules?rule=F110')
  await expect(tabB.getByRole('heading', { name: 'Try F110' })).toBeVisible()

  // Saving in tab A writes the library like this; the Save button would also
  // validate with Pyodide first, which this test does not need.
  await tabA.goto('/linti/config')
  await tabA.locator('.configurator .cm-editor').waitFor({ state: 'attached' })
  await tabA.evaluate((key) => {
    const library = JSON.parse(localStorage.getItem(key) || 'null')
      ?? { version: 1, profiles: [], draft: { yaml: '', baseId: null, name: '' } }
    const now = new Date().toISOString()
    library.profiles.push({ id: 'beta-id', name: 'Beta', yaml: 'rules: {}\n', createdAt: now, updatedAt: now })
    localStorage.setItem(key, JSON.stringify(library))
  }, LIBRARY_KEY)

  await tabB.getByRole('button', { name: 'Adjust F110 in configurator' }).click()
  await tabB.waitForURL(url => url.pathname === '/linti/config')
  await tabB.locator('.configurator .cm-editor').waitFor({ state: 'attached' })
  await expect.poll(() => storedNames(tabB)).toContain('Beta')
  await expect(tabB.locator('.config-switcher select option', { hasText: 'Beta' })).toHaveCount(1)
  await tabA.reload()
  expect(await storedNames(tabA)).toContain('Beta')
})

test('a share link pasted into the open configurator replaces the draft', async ({ page }) => {
  page.on('dialog', dialog => dialog.accept())
  await page.goto(`/linti/config${shareHash('v11', '# v11\n')}`)
  const editor = page.locator('.configurator .cm-content')
  await expect(editor).toContainText('# v11')

  await page.evaluate(hash => { location.hash = hash }, shareHash('v12', '# v12\n'))
  // v11 is an unsaved draft, so replacing it asks first.
  await page.getByRole('dialog').getByRole('button', { name: 'Replace' }).click()
  await expect(editor).toContainText('# v12')
  await expect(page).toHaveURL(url => !url.hash)

  await page.goto('/linti/playground')
  await expect(page.locator('details.config')).toContainText('v12')
})

test('choosing all categories after a ?group= link keeps the next rule listed', async ({ page }) => {
  await page.goto('/linti/rules?group=F')
  const category = page.locator('#rule-group')
  await expect(category).toContainText('F ·')
  await category.click()
  await page.getByRole('option', { name: 'All categories' }).click()
  await expect(page).toHaveURL(url => !url.searchParams.has('group'))

  await page.getByRole('button', { name: /^C150 / }).click()
  await expect(page.getByRole('heading', { name: 'Try C150' })).toBeVisible()
  await expect(category).toContainText('All categories')
  await expect(page.getByRole('button', { name: /^C150 / })).toHaveAttribute('aria-current', 'true')
})

test('canonical, og:url and sitemap keep the /linti/ subpath', async ({ page }) => {
  await page.goto('/linti/config')
  await expect(page.locator('link[rel="canonical"]')).toHaveAttribute('href', 'https://deutschebahn.github.io/linti/config')
  await expect(page.locator('meta[property="og:url"]')).toHaveAttribute('content', 'https://deutschebahn.github.io/linti/config')
  const image = await page.locator('meta[property="og:image"]').getAttribute('content')
  if (image) expect(image).not.toContain('/linti/linti/')

  const sitemap = await readFile(new URL('sitemap.xml', PUBLIC), 'utf8')
  const locations = [...sitemap.matchAll(/<loc>([^<]+)<\/loc>/g)].map(match => match[1])
  expect(locations).toContain('https://deutschebahn.github.io/linti/config')
  for (const location of locations) expect(location).toMatch(/^https:\/\/deutschebahn\.github\.io\/linti(\/|$)/)
})

test('the build links no MCP server the static site cannot serve', async () => {
  const assets = new URL('_nuxt/', PUBLIC)
  const files = await readdir(assets)
  for (const file of files.filter(name => name.endsWith('.js'))) {
    expect(await readFile(new URL(file, assets), 'utf8'), file).not.toContain('Copy MCP Server URL')
  }
})
