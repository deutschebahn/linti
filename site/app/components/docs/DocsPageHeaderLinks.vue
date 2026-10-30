<!-- Docus 5.13.0's page header menu without the MCP entries (the static
     GitHub Pages build has no /mcp endpoint) and hidden on the tool pages.
     Re-sync on Docus upgrades. -->
<script setup lang="ts">
import { useClipboard } from '@vueuse/core'
import { withTrailingSlash } from 'ufo'
import { useRuntimeConfig } from '#imports'

const route = useRoute()
const runtimeConfig = useRuntimeConfig()
const appBaseURL = runtimeConfig.app?.baseURL || '/'

const { copy, copied } = useClipboard()
const { t } = useDocusI18n()

// The interactive tool pages have no prose worth copying into a chat.
const toolPage = computed(() => ['/playground', '/rules', '/config'].includes(route.path.replace(/\/$/, '')))

const markdownLink = computed(() => `${window?.location?.origin}${withTrailingSlash(appBaseURL)}raw${route.path}.md`)
const items = computed(() => [
  [{
    label: t('docs.copy.link'),
    icon: 'i-lucide-link',
    onSelect() {
      copy(markdownLink.value)
    },
  },
  {
    label: t('docs.copy.view'),
    icon: 'i-simple-icons:markdown',
    target: '_blank',
    to: markdownLink.value,
  },
  {
    label: t('docs.copy.gpt'),
    icon: 'i-simple-icons:openai',
    target: '_blank',
    to: `https://chatgpt.com/?hints=search&q=${encodeURIComponent(`Read ${markdownLink.value} so I can ask questions about it.`)}`,
  },
  {
    label: t('docs.copy.claude'),
    icon: 'i-simple-icons:anthropic',
    target: '_blank',
    to: `https://claude.ai/new?q=${encodeURIComponent(`Read ${markdownLink.value} so I can ask questions about it.`)}`,
  }],
])

async function copyPage() {
  const page = await $fetch<string>(`/raw${route.path}.md`)
  copy(page)
}
</script>

<template>
  <UFieldGroup v-if="!toolPage" size="sm">
    <UButton
      :label="t('docs.copy.page')"
      :icon="copied ? 'i-lucide-check' : 'i-lucide-copy'"
      color="neutral"
      variant="soft"
      :ui="{
        leadingIcon: 'text-neutral size-3.5',
      }"
      @click="copyPage"
    />

    <UDropdownMenu
      size="sm"
      :items="items"
      :content="{
        align: 'end',
        side: 'bottom',
        sideOffset: 8,
      }"
    >
      <UButton
        icon="i-lucide-chevron-down"
        color="neutral"
        variant="soft"
        class="border-l border-muted"
      />
    </UDropdownMenu>
  </UFieldGroup>
</template>
