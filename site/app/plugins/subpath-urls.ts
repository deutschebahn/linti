import { joinURL, withoutTrailingSlash } from 'ufo'

/**
 * Docus builds canonical and og:url as site.url + route path and ignores
 * app.baseURL. site.url must stay a bare origin (nuxt-site-config and the OG
 * image URLs add the base themselves), so the subpath is added here.
 */
export default defineNuxtPlugin((nuxtApp) => {
  const { baseURL } = useRuntimeConfig().app
  const origin = withoutTrailingSlash(useSiteConfig().url)
  if (!origin || baseURL === '/') return
  const prefix = joinURL(origin, baseURL)
  injectHead(nuxtApp).hooks?.hook('tags:resolve', ({ tags }) => {
    for (const tag of tags) {
      const key = tag.tag === 'link' && tag.props.rel === 'canonical'
        ? 'href'
        : tag.tag === 'meta' && tag.props.property === 'og:url' ? 'content' : null
      const url = key && tag.props[key]
      if (typeof url === 'string' && url.startsWith(origin) && !url.startsWith(prefix)) {
        tag.props[key!] = joinURL(prefix, url.slice(origin.length))
      }
    }
  })
})
