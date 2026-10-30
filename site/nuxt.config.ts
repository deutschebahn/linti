// site.url stays a bare origin: nuxt-site-config rejects a path and the OG
// image URLs add app.baseURL themselves. Docus' canonical/og:url get the
// subpath from plugins/subpath-urls.ts. Its sitemap reads only environment
// variables; CI_PAGES_URL is one nuxt-site-config does not pick up as well.
process.env.CI_PAGES_URL ||= 'https://deutschebahn.github.io/linti'

export default defineNuxtConfig({
  extends: ['docus'],
  compatibilityDate: '2025-07-18',
  app: {
    baseURL: '/linti/',
  },
  site: {
    name: 'LinTi',
    url: 'https://deutschebahn.github.io',
  },
  robots: {
    robotsTxt: false,
  },
  // A static Pages build has no server for the MCP endpoint, so the header
  // menu's MCP entries are removed too (components/docs/DocsPageHeaderLinks.vue).
  mcp: {
    enabled: false,
  },
  nitro: {
    prerender: {
      routes: ['/rules', '/playground', '/config'],
      // Deep links like /rules?rule=F110 render the same page (the query is
      // applied in the browser), so crawling them only adds duplicate OG images.
      ignore: [(route: string) => route.includes('?') && !route.includes('_payload.json')],
    },
  },
})
