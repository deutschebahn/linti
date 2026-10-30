<script setup lang="ts">
import type { Finding } from '../composables/useLintiWorker'

/** Summary, LinTi warnings and the clickable findings of one lint run. */
const props = defineProps<{
  issues: Finding[]
  warnings: string[]
  emptyText: string
  /** Shown for findings without their own procedure (single-rule runs). */
  procedure?: string
  /** Link rule IDs to the rule reference (in a new tab). */
  linkRules?: boolean
}>()
const emit = defineEmits<{ jump: [issue: Finding] }>()

const { baseURL } = useRuntimeConfig().app
const errorCount = computed(() => props.issues.filter(issue => issue.severity === 'error').length)
const fixableCount = computed(() => props.issues.filter(issue => issue.fixable).length)
</script>

<template>
  <div class="findings-list">
    <p class="summary">
      <strong>{{ plural(issues.length, 'finding') }}</strong>
      <span v-if="issues.length" class="muted">
        · {{ plural(errorCount, 'error') }}, {{ plural(issues.length - errorCount, 'warning') }}, {{ fixableCount }} auto-fixable
      </span>
    </p>
    <slot />
    <ul v-if="warnings.length" class="warnings">
      <li v-for="(warning, index) in warnings" :key="index">{{ warning }}</li>
    </ul>
    <p v-if="!issues.length" class="success">{{ emptyText }}</p>
    <ol v-else class="issues">
      <li v-for="(issue, index) in issues" :key="index" :class="`severity-${issue.severity}`">
        <button type="button" class="issue" :aria-label="`Line ${issue.line}, column ${issue.column}: ${issue.message}`" @click="emit('jump', issue)">
          <span class="location">{{ issue.line }}:{{ issue.column }}</span>
          <span class="message">{{ issue.message }}</span>
        </button>
        <span class="meta">
          <a v-if="linkRules" :href="`${baseURL}rules?rule=${encodeURIComponent(issue.rule_id)}`" target="_blank" rel="noopener"><code>{{ issue.rule_id }}</code></a>
          <code v-else>{{ issue.rule_id }}</code>
          · {{ issue.procedure ?? procedure }}
          <span v-if="issue.fixable" class="fixable">auto-fix</span>
        </span>
      </li>
    </ol>
  </div>
</template>

<style scoped>
.summary { margin: .6rem 0; }
.warnings { margin: .5rem 0; padding: .6rem .8rem; border-left: 3px solid var(--ui-warning); font-size: .85rem; }
.issues { list-style: none; padding: 0; margin: 0; }
.issues li { padding: .5rem .2rem .5rem .6rem; border-bottom: 1px solid var(--ui-border); border-left: 3px solid var(--ui-error); }
.issues li.severity-warning { border-left-color: var(--ui-warning); }
.issue { display: flex; gap: .6rem; width: 100%; text-align: left; font-size: .88rem; }
.issue:hover .message { text-decoration: underline; }
.location { flex: none; min-width: 3.2rem; color: var(--ui-text-muted); font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: .8rem; padding-top: .1rem; }
.message { overflow-wrap: anywhere; }
.meta { display: block; margin: .2rem 0 0 3.8rem; font-size: .78rem; color: var(--ui-text-muted); }
.meta a { color: var(--ui-primary); }
.fixable { margin-left: .3rem; padding: 0 .4rem; border-radius: 1rem; background: color-mix(in srgb, var(--ui-success) 15%, transparent); color: var(--ui-success); }
</style>
