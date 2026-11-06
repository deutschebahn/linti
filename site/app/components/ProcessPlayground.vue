<script setup lang="ts">
import regionsExample from '../../../example/playground/process-regions.ti?raw'
import paExample from '../../../example/playground/process-pa.ti?raw'
import yamlExample from '../../../example/playground/process.yaml?raw'
import type { Finding, ProcessResult } from '../composables/useLintiWorker'
import type { CodeEditorHandle, EditorKey } from '../utils/editor'

const examples: Record<string, { label: string, code: string }> = {
  regions: { label: '.ti with #region sections', code: regionsExample },
  pa: { label: 'PA code (#SECTION)', code: paExample },
  yaml: { label: 'TM1py YAML', code: yamlExample },
}

const formatNames: Record<ProcessResult['format'], string> = {
  ti: '.ti',
  pa: 'PA code',
  yaml: 'YAML',
}

const statusLabels = {
  defaults: 'LinTi defaults',
  draft: 'unsaved local draft',
  saved: 'saved in this browser',
}

// Keep an edited process while moving to the configurator and back.
const code = useState('linti-playground-code', () => examples.regions!.code)
const editor = ref<CodeEditorHandle | null>(null)
const resultsPanel = ref<HTMLElement | null>(null)
const configs = useConfigLibrary()
const copyText = useCopyText()
const { busy, error, run: lint } = useLintiWorker()
const result = ref<ProcessResult | null>(null)
const loading = computed(() => !result.value && !error.value)
const fixSummary = ref('')
let lintTimer: ReturnType<typeof setTimeout> | undefined

const fixableCount = computed(() => result.value?.issues.filter(issue => issue.fixable).length ?? 0)
const diagnostics = computed(() => (result.value?.issues ?? []).map(issue => ({
  line: issue.line,
  column: issue.column,
  severity: issue.severity,
  source: issue.rule_id,
  message: issue.message,
})))
const keys: EditorKey[] = [
  { key: 'Mod-Enter', run: () => run() },
  { key: 'Mod-Shift-Enter', run: () => run(true) },
]

async function run(fix = false) {
  clearTimeout(lintTimer)
  const source = code.value
  const next = await lint({ action: 'process', code: source, config: configs.yaml.value, fix })
  if (!next) return
  if (fix && code.value !== source) {
    // Never overwrite edits made while the fix was being computed.
    fixSummary.value = 'The code changed while fixing; run auto-fix again.'
    scheduleLint()
    return
  }
  if (fix) {
    const total = Object.values(next.fixes).reduce((sum, count) => sum + count, 0)
    fixSummary.value = total
      ? `Applied ${plural(total, 'fix', 'fixes')}. Undo with Ctrl+Z / ⌘Z.`
      : 'Nothing to fix automatically.'
    code.value = next.code
  }
  // Findings belong to the text they were computed for; skip stale ones.
  if (code.value === (fix ? next.code : source)) result.value = next
}

function scheduleLint() {
  clearTimeout(lintTimer)
  lintTimer = setTimeout(() => run(), 500)
}

function edit(text: string) {
  code.value = text
  scheduleLint()
}

function loadExample(select: HTMLSelectElement) {
  const example = examples[select.value]
  select.value = ''
  if (!example) return
  fixSummary.value = ''
  edit(example.code)
}

function jumpTo(issue: Finding) {
  editor.value?.reveal(issue)
}

function downloadCode() {
  const extension = result.value?.format === 'yaml' ? 'yaml' : 'ti'
  const name = (result.value?.process_name || 'process').replace(/[^\w.-]+/g, '_')
  downloadText(`${name}.${extension}`, code.value)
}

watch(configs.yaml, scheduleLint)
onMounted(() => run())
onBeforeUnmount(() => clearTimeout(lintTimer))
</script>

<template>
  <div class="lint-tool">
    <ConfirmDialog />
    <div class="playground">
      <div class="toolbar">
        <label class="example-picker">
          <span>Load example</span>
          <select class="field" @change="loadExample($event.target as HTMLSelectElement)">
            <option value="">Choose…</option>
            <option v-for="(example, key) in examples" :key="key" :value="key">{{ example.label }}</option>
          </select>
        </label>
        <span class="spacer" />
        <div class="toolbar-actions">
          <UButton color="neutral" variant="outline" icon="i-lucide-play" :disabled="busy" title="Ctrl+Enter / ⌘Enter" @click="run()">Lint</UButton>
          <UButton icon="i-lucide-wand-sparkles" :disabled="busy || !fixableCount" title="Ctrl+Shift+Enter / ⌘⇧Enter" @click="run(true)">
            Auto-fix{{ fixableCount ? ` (${fixableCount})` : '' }}
          </UButton>
          <UButton color="neutral" variant="ghost" icon="i-lucide-copy" @click="copyText(code, 'Code')">Copy</UButton>
          <UButton color="neutral" variant="ghost" icon="i-lucide-download" @click="downloadCode()">Download</UButton>
        </div>
        <!-- Stacked layout: the findings are below the editor, out of sight. -->
        <button v-if="result" type="button" class="result-jump" @click="resultsPanel?.scrollIntoView({ behavior: 'smooth', block: 'start' })">
          <strong>{{ plural(result.issues.length, 'finding') }}</strong><template v-if="fixableCount"> · {{ fixableCount }} auto-fixable</template>
          <span aria-hidden="true">↓</span>
        </button>
      </div>

      <div class="layout">
        <div class="editor-column">
          <CodeEditor ref="editor" class="editor" :model-value="code" label="TI process source" :diagnostics="diagnostics" :keys="keys" @update:model-value="edit" />
          <details class="config" :open="configs.status.value !== 'defaults'">
            <summary>
              Configuration: {{ configs.label.value }}
              <span class="badge">{{ statusLabels[configs.status.value] }}</span>
            </summary>
            <pre class="config-editor"><code>{{ configs.yaml.value }}</code></pre>
            <p class="config-hint">
              Configure or save this YAML in the <NuxtLink :to="{ path: '/config', query: { from: 'playground' } }">configurator</NuxtLink>.
            </p>
          </details>
        </div>

        <section ref="resultsPanel" class="results" aria-live="polite" aria-label="Findings">
          <p v-if="loading" class="status">Loading LinTi in your browser… the first run downloads Pyodide.</p>
          <p v-if="result" class="status">
            <span class="badge">{{ formatNames[result.format] }}</span>
            <span class="badge">{{ result.process_name }}</span>
            <span v-if="busy" class="muted">checking…</span>
          </p>
          <p v-if="error" role="alert" class="error">{{ error }}</p>
          <FindingsList v-if="result" :issues="result.issues" :warnings="result.warnings" empty-text="No findings. 🎉" link-rules @jump="jumpTo">
            <p v-if="fixSummary" class="success">{{ fixSummary }}</p>
          </FindingsList>
        </section>
      </div>
    </div>
  </div>
</template>

<style scoped>
.lint-tool { container-type: inline-size; }
.playground { min-width: 0; }
.toolbar { display: flex; flex-wrap: wrap; gap: .5rem; align-items: end; margin-bottom: .8rem; }
.example-picker { display: flex; flex-direction: column; gap: .25rem; font-size: .8rem; font-weight: 650; }
.spacer { flex: 1; }
.toolbar-actions { display: flex; flex-wrap: wrap; gap: .5rem; }
/* Native select: the phone's own picker is the most usable one there. */
.field { min-height: 2.25rem; border: 1px solid var(--ui-border-accented); border-radius: .4rem; padding: .4rem .6rem; color: var(--ui-text); background: var(--ui-bg); font-weight: 400; }
.result-jump { display: none; width: 100%; padding: .55rem .8rem; border: 1px solid var(--ui-border); border-radius: .45rem; background: var(--ui-bg-elevated); text-align: left; font-size: .9rem; }
.result-jump span { float: right; color: var(--ui-text-muted); }
.layout { display: grid; grid-template-columns: minmax(0, 3fr) minmax(16rem, 2fr); gap: 1.2rem; align-items: start; }
.editor-column { min-width: 0; }
.editor { --editor-height: min(70dvh, 40rem); }
.config-hint a { color: var(--ui-primary); }
.config { margin-top: .8rem; }
.config summary { cursor: pointer; font-size: .9rem; font-weight: 600; }
.config-editor { overflow-x: auto; max-height: 16rem; padding: .7rem; border: 1px solid var(--ui-border); border-radius: .4rem; background: var(--ui-bg); font: .82rem/1.5 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }
.config-hint { margin-top: .4rem; font-size: .8rem; color: var(--ui-text-muted); }
.config summary .badge { margin-left: .4rem; font-weight: 500; }
.results { position: sticky; top: calc(var(--ui-header-height) + 1rem); max-height: calc(100vh - var(--ui-header-height) - 2rem); scroll-margin-top: calc(var(--ui-header-height) + 1rem); overflow-y: auto; padding: 1rem; border: 1px solid var(--ui-border); border-radius: .5rem; background: var(--ui-bg-elevated); }
.status { display: flex; gap: .4rem; align-items: center; flex-wrap: wrap; font-size: .88rem; }
.error { white-space: pre-wrap; }
/* The layout follows the space the page gives it, not the viewport. */
@container (max-width: 760px) {
  .layout { grid-template-columns: minmax(0, 1fr); }
  .results { position: static; max-height: none; }
  .editor { --editor-height: 55dvh; }
  .result-jump { display: block; }
}
@container (max-width: 560px) {
  .toolbar { display: grid; grid-template-columns: minmax(0, 1fr); }
  .example-picker { min-width: 0; }
  .example-picker .field { box-sizing: border-box; width: 100%; }
  .spacer { display: none; }
  .toolbar-actions { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .toolbar-actions > * { min-width: 0; justify-content: center; white-space: nowrap; }
}
@media (max-width: 760px) {
  /* 16px text on phones keeps iOS Safari from zooming in when a field gets focus. */
  .field { font-size: 1rem; }
}
@media (pointer: coarse) {
  .toolbar-actions > * { min-height: 2.75rem; }
  .field { min-height: 2.75rem; }
}
</style>
