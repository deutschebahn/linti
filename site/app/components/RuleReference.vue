<script setup lang="ts">
import rules from '../data/rules.json'
import type { Finding, LintRequest, RuleResult } from '../composables/useLintiWorker'
import type { CodeEditorHandle } from '../utils/editor'

type Example = {
  code: string
  description: string
  valid: boolean
  procedure: string
  config: string
  parameters: string[]
  variables: string[]
  datasource_type: string | null
  datasource_query: string | null
}
type Rule = {
  id: string
  name: string
  description: string
  explanation: string
  group: string
  group_name: string
  severity: string
  auto_fix: boolean
  enabled_by_default: boolean
  config_key: string
  config_example: string
  default_config: string
  deprecated_by: string | null
  previous_ids: string[]
  examples: Example[]
}
const DEFAULT_RULE = 'C150'

const allRules = rules as Rule[]
const configs = useConfigLibrary()
const { ask } = useConfirm()
const route = useRoute()
const router = useRouter()
const query = ref('')
const groups = [...new Set(allRules.map(rule => rule.group))]
const group = ref('all')
const groupItems = [
  { label: 'All categories', value: 'all' },
  ...groups.map(letter => ({ label: `${letter} · ${allRules.find(rule => rule.group === letter)?.group_name}`, value: letter })),
]
const procedureItems = [
  { label: 'Prolog', value: 'prolog' },
  { label: 'Metadata', value: 'metadata' },
  { label: 'Data', value: 'data' },
  { label: 'Epilog', value: 'epilog' },
]
// 16px text on phones keeps iOS Safari from zooming in when a field gets focus.
const fieldUi = { base: 'text-base sm:text-sm' }
// Starts at the default on both server and client; the ?rule= deep link is
// applied in onMounted so the prerendered HTML and hydration agree.
const selectedId = ref(DEFAULT_RULE)
const selected = computed(() => allRules.find(rule => rule.id === selectedId.value) || allRules[0]!)
const editor = ref<CodeEditorHandle | null>(null)
const detail = ref<HTMLElement | null>(null)

// The example being edited; kept across a visit to the configurator.
const code = ref('')
const procedure = ref('prolog')
const exampleConfig = ref('')
const parameters = ref('')
const variables = ref('')
const datasourceType = ref('')
const datasourceQuery = ref('')
const inputs = { code, procedure, exampleConfig, parameters, variables, datasourceType, datasourceQuery }
type Inputs = { [Key in keyof typeof inputs]: string }
const draft = useState<{ ruleId: string, usingWorkingConfig: boolean, inputs: Inputs } | null>('linti-rule-reference-draft', () => null)

const usingWorkingConfig = ref(false)
const lintiYaml = computed(() => usingWorkingConfig.value ? configs.yaml.value : exampleConfig.value)
const configLabel = computed(() => usingWorkingConfig.value
  ? `${configs.label.value}${configs.status.value === 'draft' ? ' (local draft)' : configs.status.value === 'saved' ? ' (saved in this browser)' : ''}`
  : exampleConfig.value.trim() ? 'Example settings' : 'LinTi defaults')

// Only the context an example actually uses is shown; the rest can be added.
type ContextField = 'parameters' | 'variables' | 'datasource'
const contextLabels: Record<ContextField, string> = {
  parameters: 'Parameters',
  variables: 'Variables',
  datasource: 'Data source',
}
const contextFields = Object.keys(contextLabels) as ContextField[]
const shownContext = ref<ContextField[]>([])
const hiddenContext = computed(() => contextFields.filter(field => !shownContext.value.includes(field)))
const contextInUse = () => contextFields.filter(field => ({
  parameters: parameters.value,
  variables: variables.value,
  datasource: datasourceType.value || datasourceQuery.value,
})[field])

function addContext(field: ContextField) {
  shownContext.value = [...shownContext.value, field]
}

function removeContext(field: ContextField) {
  shownContext.value = shownContext.value.filter(item => item !== field)
  if (field === 'parameters') parameters.value = ''
  if (field === 'variables') variables.value = ''
  if (field === 'datasource') datasourceType.value = datasourceQuery.value = ''
}

const { busy, error, run: lint } = useLintiWorker()
const result = ref<RuleResult | null>(null)
const filtered = computed(() => allRules.filter((rule) => {
  if (group.value !== 'all' && rule.group !== group.value) return false
  const text = `${rule.id} ${rule.name} ${rule.description} ${rule.explanation}`.toLowerCase()
  return text.includes(query.value.toLowerCase().trim())
}))

async function openRuleInConfigurator() {
  if (!usingWorkingConfig.value) {
    const source = exampleConfig.value || presetText(presets[0]!)
    if (configs.dirty.value && configs.yaml.value !== source
      && !(await ask('Replace the current unsaved configuration with this example?'))) return
    configs.startDraft(`${selected.value.id} variant`, source)
  }
  // Nuxt applies anchor scrolling after its own navigation scroll has settled.
  void navigateTo({
    path: '/config',
    query: { from: 'rules', rule: selected.value.id },
    hash: `#rule-${selected.value.config_key}`,
  })
}

function useExampleSettings() {
  usingWorkingConfig.value = false
  void router.replace({ query: { ...route.query, config: undefined } })
}

function chooseExample(example?: Example) {
  code.value = example?.code || 'nValue=1;'
  procedure.value = example?.procedure || 'prolog'
  exampleConfig.value = example?.config || ''
  parameters.value = example?.parameters.join(', ') || ''
  variables.value = example?.variables.join(', ') || ''
  datasourceType.value = example?.datasource_type || ''
  datasourceQuery.value = example?.datasource_query || ''
  shownContext.value = contextInUse()
  result.value = null
  error.value = ''
}

function selectRule(rule: Rule) {
  selectedId.value = rule.id
  usingWorkingConfig.value = false
  void router.replace({ query: { ...route.query, rule: rule.id, config: undefined } })
  // Stacked layout (phones, narrow tablets): the detail sits below the list.
  const section = detail.value
  if (section && section.getBoundingClientRect().top > window.innerHeight * 0.6) {
    void nextTick(() => section.scrollIntoView({ behavior: 'smooth', block: 'start' }))
  }
}

// Reset the example synchronously, before applyQuery applies its config mode.
watch(selected, (rule) => {
  usingWorkingConfig.value = false
  chooseExample(rule.examples.find(example => !example.valid) || rule.examples[0])
}, { immediate: true, flush: 'sync' })
// The page is prerendered without a query string, so URL state is applied only
// after hydration to keep the server and client markup identical.
function applyQuery(initial = false) {
  const letter = String(route.query.group || '').toUpperCase()
  const id = String(route.query.rule || '').toUpperCase()
  const rule = allRules.find(item => item.id === id)
  if (groups.includes(letter)) {
    group.value = letter
    // A bare ?group= link opens on that category's first rule.
    if (initial && !rule && selected.value.group !== letter) selectedId.value = allRules.find(item => item.group === letter)!.id
  }
  if (rule) {
    const opened = initial || selectedId.value !== rule.id
    selectedId.value = rule.id
    // A linked rule must not open hidden behind another category's filter.
    if (opened && group.value !== 'all' && group.value !== rule.group) group.value = 'all'
  }
  if (route.query.config === 'working') usingWorkingConfig.value = true
}

onMounted(async () => {
  applyQuery(true)
  await nextTick()
  const previous = draft.value
  if (!previous || previous.ruleId !== selectedId.value) return
  for (const key of Object.keys(inputs) as (keyof Inputs)[]) inputs[key].value = previous.inputs[key]
  if (route.query.config !== 'working') usingWorkingConfig.value = previous.usingWorkingConfig
  shownContext.value = contextInUse()
})
watch(() => [route.query.rule, route.query.group], () => applyQuery())
// The URL follows the category filter, so a later rule change cannot restore a stale ?group=.
watch(group, (value) => {
  const wanted = value === 'all' ? undefined : value
  if (String(route.query.group || '').toUpperCase() !== (wanted ?? '')) {
    void router.replace({ query: { ...route.query, group: wanted } })
  }
})
watch(() => route.query.config, value => (usingWorkingConfig.value = value === 'working'))

const splitNames = (text: string) => text.split(/[\s,]+/).filter(Boolean)

function request(fix: boolean): LintRequest & { action: 'rule' } {
  return {
    action: 'rule',
    code: code.value,
    procedure: procedure.value,
    ruleId: selected.value.id,
    fix,
    context: {
      config: lintiYaml.value,
      parameters: splitNames(parameters.value),
      variables: splitNames(variables.value),
      datasource_type: datasourceType.value.trim(),
      datasource_query: datasourceQuery.value.trim(),
    },
  }
}

async function run(fix = false) {
  if (busy.value || !import.meta.client) return
  result.value = null
  const sent = request(fix)
  const next = await lint(sent)
  // A result is only shown for the input it was computed from.
  if (!next || JSON.stringify(request(fix)) !== JSON.stringify(sent)) return
  result.value = next
  if (fix) code.value = next.code
}

function jumpTo(issue: Finding) {
  editor.value?.reveal(issue)
}

onBeforeUnmount(() => {
  const values = Object.fromEntries(Object.entries(inputs).map(([key, input]) => [key, input.value])) as Inputs
  draft.value = { ruleId: selectedId.value, usingWorkingConfig: usingWorkingConfig.value, inputs: values }
})
</script>

<template>
  <div class="lint-tool">
    <ConfirmDialog />
    <div class="reference">
      <div class="reference-sidebar">
        <label class="field-label" for="rule-search">Find a rule</label>
        <UInput id="rule-search" v-model="query" type="search" icon="i-lucide-search" size="lg" placeholder="ID, name, description…" class="w-full" :ui="fieldUi" />
        <label class="field-label" for="rule-group">Category</label>
        <USelect id="rule-group" v-model="group" :items="groupItems" icon="i-lucide-list-filter" size="lg" class="w-full" :ui="fieldUi" />
        <p class="rule-count">{{ filtered.length }} of {{ allRules.length }} rules</p>
        <div class="rule-list" role="list" aria-label="LinTi rules">
          <button
            v-for="rule in filtered"
            :key="rule.id"
            class="rule-choice"
            :class="{ active: selected.id === rule.id }"
            :aria-current="selected.id === rule.id ? 'true' : undefined"
            @click="selectRule(rule)"
          >
            <span class="rule-choice-title"><code>{{ rule.id }}</code> {{ rule.name }}</span>
            <span class="rule-choice-description">{{ rule.description }}</span>
          </button>
          <p v-if="!filtered.length" class="empty">No matching rules.</p>
        </div>
      </div>

      <section v-if="selected" ref="detail" class="rule-detail" :aria-label="`${selected.id}: ${selected.name}`">
        <div class="rule-header">
          <span class="rule-code">{{ selected.id }}</span>
          <span class="badge">{{ selected.group_name }}</span>
          <span class="badge">{{ selected.severity }}</span>
          <span v-if="selected.auto_fix" class="badge">Auto-fix</span>
        </div>
        <h2>{{ selected.name }}</h2>
        <p class="lede">{{ selected.description }}</p>
        <p v-if="selected.deprecated_by" class="notice">Deprecated; use {{ selected.deprecated_by }} instead.</p>
        <p v-if="selected.previous_ids.length" class="muted">Previous ID: {{ selected.previous_ids.join(', ') }}</p>
        <div v-if="selected.explanation" class="explanation">{{ selected.explanation }}</div>

        <div class="playground">
          <h3>Try {{ selected.id }}</h3>
          <p>Edit an example and run the real Python rule in your browser. The first run loads Pyodide; subsequent runs reuse it.</p>
          <div v-if="selected.examples.length" class="example-actions">
            <UButton
              v-for="(example, index) in selected.examples"
              :key="index"
              :icon="example.valid ? 'i-lucide-circle-check' : 'i-lucide-circle-x'"
              color="neutral"
              variant="outline"
              size="sm"
              class="example-button"
              @click="chooseExample(example)"
            >
              {{ example.description || (example.valid ? 'Valid example' : 'Invalid example') }}
            </UButton>
          </div>
          <label class="field-label" for="procedure">TI procedure</label>
          <USelect id="procedure" v-model="procedure" :items="procedureItems" size="lg" class="w-44 max-w-full" :ui="fieldUi" />
          <span class="field-label">TI code</span>
          <CodeEditor ref="editor" v-model="code" class="code-editor" label="TI code" />
          <div class="config-handoff">
            <details class="config-inspection">
              <summary>Configuration used: {{ configLabel }}</summary>
              <div class="config-inspection-body">
                <p v-if="!lintiYaml.trim()" class="muted">This example uses LinTi's default configuration.</p>
                <p v-if="!lintiYaml.trim() && !selected.enabled_by_default" class="muted">Running {{ selected.id }} here selects the rule explicitly, so the ‘<code>enabled: false</code>’ setting from the default config is overwritten.</p>
                <p v-if="lintiYaml.trim()" class="muted">This YAML is used for the run:</p>
                <pre v-if="lintiYaml.trim()"><code>{{ lintiYaml }}</code></pre>
                <template v-else-if="selected.default_config">
                  <p class="muted">Default values for {{ selected.id }} in a full scan:</p>
                  <pre><code>{{ selected.default_config }}</code></pre>
                </template>
                <p v-if="lintiYaml.trim()" class="muted">Running {{ selected.id }} here selects the rule explicitly. If this YAML sets <code>enabled: false</code>, that setting is overwritten for this run.</p>
                <button v-if="usingWorkingConfig" type="button" class="text-action" @click="useExampleSettings()">Use example settings instead</button>
              </div>
            </details>
            <UButton icon="i-lucide-sliders-horizontal" color="neutral" variant="outline" size="sm" @click="openRuleInConfigurator()">Adjust {{ selected.id }} in configurator</UButton>
          </div>
          <div v-if="shownContext.length" class="context">
            <p class="context-title">Runs with</p>
            <div v-for="field in shownContext" :key="field" class="context-field">
              <div class="context-label">
                <label class="field-label" :for="`context-${field}`">{{ contextLabels[field] }}</label>
                <UButton
                  size="sm"
                  color="neutral"
                  variant="ghost"
                  icon="i-lucide-x"
                  :aria-label="`Remove ${contextLabels[field]}`"
                  @click="removeContext(field)"
                />
              </div>
              <UInput v-if="field === 'parameters'" id="context-parameters" v-model="parameters" placeholder="pYear, pVersion" class="w-full" :ui="fieldUi" />
              <UInput v-else-if="field === 'variables'" id="context-variables" v-model="variables" placeholder="vRegion, vAmount" class="w-full" :ui="fieldUi" />
              <div v-else class="datasource-fields">
                <UInput id="context-datasource" v-model="datasourceType" placeholder="ODBC" aria-label="Data source type" :ui="fieldUi" />
                <UInput v-model="datasourceQuery" placeholder="SELECT … FROM …" aria-label="Data source query" class="w-full" :ui="fieldUi" />
              </div>
            </div>
          </div>
          <div v-if="hiddenContext.length" class="context-add">
            <span class="muted">Add:</span>
            <UButton
              v-for="field in hiddenContext"
              :key="field"
              size="sm"
              color="neutral"
              variant="soft"
              icon="i-lucide-plus"
              @click="addContext(field)"
            >
              {{ contextLabels[field] }}
            </UButton>
          </div>
          <div class="run-actions">
            <UButton icon="i-lucide-play" :loading="busy" @click="run()">{{ busy ? 'Loading LinTi / checking…' : `Run ${selected.id}` }}</UButton>
            <UButton v-if="selected.auto_fix" icon="i-lucide-wand-sparkles" color="neutral" variant="outline" :disabled="busy" @click="run(true)">Apply auto-fix</UButton>
          </div>
          <p v-if="error" role="alert" class="error">{{ error }}</p>
          <FindingsList v-if="result" class="findings" aria-live="polite" aria-label="Findings" :issues="result.issues" :warnings="result.warnings" :procedure="procedure" :empty-text="`No findings for ${selected.id}. 🎉`" @jump="jumpTo">
            <p v-if="result.fixes" class="success">Applied {{ plural(result.fixes, 'fix', 'fixes') }}.</p>
          </FindingsList>
        </div>

      </section>
    </div>
  </div>
</template>

<style scoped>
.lint-tool { container-type: inline-size; }
.reference { display: grid; grid-template-columns: minmax(14rem, 19rem) minmax(0, 1fr); gap: 2rem; align-items: start; }
.reference-sidebar { position: sticky; top: calc(var(--ui-header-height) + 1rem); max-height: calc(100vh - var(--ui-header-height) - 2rem); display: flex; flex-direction: column; min-width: 0; }
.field-label { display: block; margin: .7rem 0 .35rem; font-size: .85rem; font-weight: 650; }
.rule-count { margin: .5rem 0; color: var(--ui-text-muted); font-size: .85rem; }
.code-editor { --editor-height: 15rem; }
.rule-list { overflow-y: auto; border: 1px solid var(--ui-border); border-radius: .5rem; }
.rule-choice { display: block; width: 100%; padding: .7rem .8rem; text-align: left; border-bottom: 1px solid var(--ui-border); }
.rule-choice:hover, .rule-choice.active { background: var(--ui-bg-elevated); }
.rule-choice.active { box-shadow: inset 3px 0 var(--ui-primary); }
.rule-choice-title { display: block; font-size: .9rem; font-weight: 650; }
.rule-choice-description { display: -webkit-box; overflow: hidden; -webkit-line-clamp: 2; -webkit-box-orient: vertical; margin-top: .15rem; color: var(--ui-text-muted); font-size: .8rem; line-height: 1.35; }
.rule-detail { min-width: 0; scroll-margin-top: calc(var(--ui-header-height) + 1rem); }
.rule-header, .example-actions, .run-actions { display: flex; gap: .5rem; flex-wrap: wrap; align-items: center; }
.rule-code { font-size: 1.15rem; font-weight: 750; color: var(--ui-primary); }
.rule-detail h2 { margin: .8rem 0 .5rem; font-size: 1.8rem; font-weight: 720; }
.lede { font-size: 1.07rem; }
.explanation { margin: 1.4rem 0; white-space: pre-wrap; line-height: 1.65; }
.notice { padding: .7rem; border-left: 3px solid var(--ui-warning); background: var(--ui-bg-elevated); }
.playground { padding: 1.2rem; border: 1px solid var(--ui-border); border-radius: .65rem; background: var(--ui-bg-elevated); }
.playground h3 { font-size: 1.2rem; font-weight: 700; margin-bottom: .3rem; }
.playground p { font-size: .9rem; }
.example-actions { margin: 1rem 0; }
.example-button { max-width: 100%; text-align: left; white-space: normal; }
.run-actions { margin-top: .8rem; }
.context { margin-top: .8rem; padding: .2rem .8rem .8rem; border: 1px solid var(--ui-border-accented); border-left: 3px solid var(--ui-primary); border-radius: .45rem; background: var(--ui-bg); }
.context-title { margin: .5rem 0 0; font-size: .75rem; font-weight: 650; letter-spacing: .04em; text-transform: uppercase; color: var(--ui-text-muted); }
.context-label { display: flex; align-items: end; justify-content: space-between; gap: .5rem; }
.datasource-fields { display: grid; grid-template-columns: 7rem minmax(0, 1fr); gap: .5rem; }
.context-add { display: flex; flex-wrap: wrap; align-items: center; gap: .4rem; margin-top: .7rem; }
.findings { margin-top: 1rem; padding: 1rem; border: 1px solid var(--ui-border); border-radius: .5rem; background: var(--ui-bg); }
.config-handoff { display: flex; flex-wrap: wrap; align-items: flex-start; gap: .5rem; margin-top: .7rem; }
.config-inspection { flex: 1 1 16rem; min-width: 0; border: 1px solid var(--ui-border); border-radius: .4rem; background: var(--ui-bg); }
.config-inspection summary { padding: .4rem .6rem; cursor: pointer; color: var(--ui-text-muted); font-size: .85rem; }
.config-inspection-body { padding: 0 .6rem .6rem; font-size: .85rem; }
.config-inspection-body p { margin: .3rem 0; }
.config-inspection-body pre { margin: .5rem 0; padding: .6rem; overflow-x: auto; border-radius: .4rem; background: var(--ui-bg-elevated); }
.text-action { color: var(--ui-primary); text-decoration: underline; text-underline-offset: .15rem; }
.empty { padding: .8rem; }
/* The layout follows the space the page gives it, not the viewport: Docus'
   navigation column takes a third of a tablet screen. */
@container (max-width: 680px) {
  .reference { grid-template-columns: minmax(0, 1fr); gap: 1.5rem; }
  .reference-sidebar { position: static; max-height: none; }
  .rule-list { max-height: 15rem; }
  .playground { padding: 1rem; }
}
@media (pointer: coarse) {
  .context-label :deep(button) { min-width: 2.75rem; min-height: 2.75rem; justify-content: center; }
}
</style>
