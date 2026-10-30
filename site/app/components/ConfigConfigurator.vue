<script setup lang="ts">
import type { CodeEditorHandle, EditorDiagnostic } from '../utils/editor'
import ConfigLibraryPanel from './ConfigLibraryPanel.vue'

const route = useRoute()
const configs = useConfigLibrary()
const copyText = useCopyText()
const fromRules = computed(() => route.query.from === 'rules')
const returnLink = computed(() => {
  if (route.query.from === 'playground') return { to: '/playground', label: 'Back to playground' }
  if (!fromRules.value) return null
  const id = String(route.query.rule || '').toUpperCase()
  const known = ruleCards.some(card => card.rules.some(rule => rule.id === id))
  return known
    ? { to: `/rules?rule=${encodeURIComponent(id)}&config=working`, label: `Back to rule ${id}` }
    : { to: '/rules?config=working', label: 'Back to rule reference' }
})

const editor = ref<CodeEditorHandle | null>(null)
const panel = ref<InstanceType<typeof ConfigLibraryPanel> | null>(null)
const fileInput = ref<HTMLInputElement | null>(null)
const parsed = shallowRef<ParsedConfig>(parseConfig(''))
/** The YAML the form currently reflects (the editor's text as last parsed). */
const yamlText = ref('')
const query = ref('')
const onlyChanged = ref(false)
const highlighted = ref('')
const openCards = ref(new Set<string>())
const mobilePane = ref<'form' | 'yaml'>('form')
const shareError = ref('')

// Typing reaches the shared draft at once and the form after a short pause.
let typed: string | null = null
let parseTimer: ReturnType<typeof setTimeout> | undefined

const data = computed(() => parsed.value.data)
const locked = computed(() => parsed.value.parseErrors.length > 0)
const issues = computed(() => (locked.value ? [] : validateConfig(data.value)))
const allFields = [...topLevelFields, ...ruleCards.flatMap(card => card.fields)]
const changedCount = computed(() => allFields.filter(field => isChanged(data.value, field)).length)
const errorCount = computed(() => parsed.value.parseErrors.length + issues.value.filter(issue => issue.level === 'error').length)
const warningCount = computed(() => issues.value.filter(issue => issue.level === 'warning').length)
const diagnostics = computed<EditorDiagnostic[]>(() => [
  ...parsed.value.parseErrors.map(error => ({ from: error.from, to: error.to, severity: 'error' as const, message: error.message })),
  ...issues.value.map(issue => ({ ...(rangeOf(parsed.value.doc, issue.path) ?? { from: 0, to: 0 }), severity: issue.level, message: issue.message })),
])

const groups = computed(() => {
  const needle = query.value.toLowerCase().trim()
  const visible = ruleCards.filter((card) => {
    if (onlyChanged.value && !cardChanged(card)) return false
    if (!needle) return true
    const haystack = `${card.configKey} ${card.title} ${card.description} ${card.rules.map(rule => `${rule.id} ${rule.name}`).join(' ')}`
    return haystack.toLowerCase().includes(needle)
  })
  const byGroup = new Map<string, { name: string, cards: RuleCard[] }>()
  for (const card of visible) {
    const group = byGroup.get(card.group) ?? { name: card.groupName, cards: [] }
    group.cards.push(card)
    byGroup.set(card.group, group)
  }
  return [...byGroup.entries()].map(([letter, group]) => ({ letter, ...group }))
})

function valueOf(field: FieldSpec) {
  return effectiveValue(data.value, field)
}

function changed(field: FieldSpec) {
  return isChanged(data.value, field)
}

function issueFor(field: FieldSpec) {
  const path = field.path.join('.')
  return issues.value.find(issue => issue.path.join('.') === path)
}

/** Hidden fields (deprecated spellings) appear only while the YAML sets them. */
function visibleFields(fields: FieldSpec[]) {
  return fields.filter(field => !field.hidden || changed(field) || issueFor(field))
}

function cardField(card: RuleCard, key: string) {
  return card.fields.find(field => field.key === key)!
}

function cardOptions(card: RuleCard) {
  return visibleFields(card.fields.filter(field => field.key !== 'enabled'))
}

function cardChanged(card: RuleCard) {
  return card.fields.some(field => changed(field))
}

function cardIssues(card: RuleCard) {
  const prefix = `rules.${card.configKey}`
  return issues.value.filter(issue => issue.path.join('.') === prefix)
}

/** Open when the visitor opened it, or while one of its options has a problem. */
function isOpen(card: RuleCard) {
  const prefix = `rules.${card.configKey}.`
  return openCards.value.has(card.configKey) || issues.value.some(issue => `${issue.path.join('.')}.`.startsWith(prefix))
}

function toggleCard(card: RuleCard, open: boolean) {
  const next = new Set(openCards.value)
  if (open) next.add(card.configKey)
  else next.delete(card.configKey)
  openCards.value = next
}

function severityLabel(card: RuleCard) {
  const declared = [...new Set(card.rules.map(rule => rule.severity))].join(' / ')
  return `Rule default (${declared})`
}

/** Show *text* in the editor and the form, and make it the working draft. */
function load(text: string) {
  clearTimeout(parseTimer)
  typed = null
  yamlText.value = text
  parsed.value = parseConfig(text)
  configs.yaml.value = text
}

/** A different configuration: also open the cards it changes. */
function setWorking(text: string) {
  load(text)
  openCards.value = new Set(ruleCards.filter(card => cardChanged(card)).map(card => card.configKey))
}

function onType(text: string) {
  typed = text
  configs.yaml.value = text
  clearTimeout(parseTimer)
  parseTimer = setTimeout(() => load(text), 200)
}

function updateField(field: FieldSpec, value: unknown) {
  // Typing that is still waiting for its pause comes first.
  if (typed !== null) load(typed)
  if (locked.value) return
  const { doc } = parsed.value
  setOption(doc, field.path, value, field.default)
  load(stringifyConfig(doc))
}

async function copyShareLink() {
  const link = shareLink(configs.label.value, configs.yaml.value)
  shareError.value = link ? '' : 'This configuration is too large for a link. Download its YAML instead.'
  if (link) await copyText(link, 'Share link')
}

async function openFile(input: HTMLInputElement) {
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  const text = await file.text()
  void panel.value?.guard(() => configs.startDraft(file.name.replace(/\.ya?ml$/i, ''), text))
}

const moreActions = [[
  { label: 'Copy YAML', icon: 'i-lucide-copy', onSelect: () => void copyText(configs.yaml.value, 'linti.yaml') },
  { label: 'Copy share link', icon: 'i-lucide-link', onSelect: () => void copyShareLink() },
  { label: 'Open file…', icon: 'i-lucide-upload', onSelect: () => fileInput.value?.click() },
]]

function focusIssue(issue: ConfigIssue) {
  const range = rangeOf(parsed.value.doc, issue.path)
  mobilePane.value = 'yaml'
  if (range) void nextTick(() => editor.value?.reveal(range))
}

/** `?rule=F110` (or `?rule=keyword_casing`): open, reveal and flash that card. */
function applyRuleQuery() {
  const wanted = String(route.query.rule || '')
  if (!wanted) return
  const card = ruleCards.find(item => item.configKey === wanted || item.rules.some(rule => rule.id === wanted.toUpperCase()))
  if (!card) return
  query.value = ''
  onlyChanged.value = false
  mobilePane.value = 'form'
  toggleCard(card, true)
  highlighted.value = card.configKey
  // Links from the rule reference use an anchor, so Nuxt owns their scrolling.
  // Scrolling here would race its later navigation scroll on a cached visit.
  if (route.hash !== `#rule-${card.configKey}`) {
    void nextTick(() => document.getElementById(`rule-${card.configKey}`)?.scrollIntoView({ block: 'center', behavior: 'smooth' }))
  }
  setTimeout(() => (highlighted.value = ''), 2500)
}

watch(() => route.query.rule, applyRuleQuery)
// Switching profiles, share links and uploads replace the draft from outside.
watch(configs.yaml, (text) => {
  if (text !== yamlText.value && text !== typed) setWorking(text)
})
watch(mobilePane, pane => pane === 'yaml' && nextTick(() => editor.value?.measure()))

onMounted(() => {
  // Nothing is stored until the visitor changes something: the recommended
  // preset is what LinTi does without a linti.yaml anyway.
  setWorking(configs.yaml.value)
  // Open the target before Nuxt's post-navigation anchor scroll.
  applyRuleQuery()
})
onBeforeUnmount(() => clearTimeout(parseTimer))
</script>

<template>
  <div class="lint-tool">
    <ConfirmDialog />
    <div class="configurator">
      <nav v-if="returnLink" class="return-links" aria-label="Continue with your configuration">
        <UButton :to="returnLink.to" icon="i-lucide-arrow-left" color="neutral" variant="soft" size="sm">{{ returnLink.label }}</UButton>
        <UButton v-if="!fromRules" to="/rules" icon="i-lucide-list" color="neutral" variant="ghost" size="sm">Rule reference</UButton>
      </nav>
      <ConfigLibraryPanel ref="panel" />
      <div class="pane-switch" role="group" aria-label="Show">
        <button type="button" :aria-pressed="mobilePane === 'form'" :class="{ active: mobilePane === 'form' }" @click="mobilePane = 'form'">Form</button>
        <button type="button" :aria-pressed="mobilePane === 'yaml'" :class="{ active: mobilePane === 'yaml' }" @click="mobilePane = 'yaml'">linti.yaml</button>
      </div>

      <div class="layout">
        <div class="form-pane" :class="{ hidden: mobilePane !== 'form' }">
          <p v-if="locked" role="alert" class="banner error">
            The YAML has a syntax error, so the form is paused. Fix it on the right and the form picks it up again.
          </p>
          <fieldset :disabled="locked" class="form">
            <section class="form-section">
              <h2>Run settings</h2>
              <ConfigField
                v-for="field in visibleFields(runFields)"
                :key="field.key"
                :field="field"
                :value="valueOf(field)"
                :changed="changed(field)"
                :issue="issueFor(field)"
                :disabled="locked"
                :unset-label="field.key === 'target_version' ? 'Not set (each rule\'s default)' : undefined"
                @update="updateField(field, $event)"
              />
              <details class="limits">
                <summary>Input limits</summary>
                <ConfigField
                  v-for="field in limitFields"
                  :key="field.key"
                  :field="field"
                  :value="valueOf(field)"
                  :changed="changed(field)"
                  :issue="issueFor(field)"
                  :disabled="locked"
                  @update="updateField(field, $event)"
                />
              </details>
            </section>

            <section class="form-section">
              <h2>Rules</h2>
              <div class="rule-filters">
                <UInput v-model="query" type="search" icon="i-lucide-search" placeholder="Filter by ID, name, key…" aria-label="Filter rules" class="grow" :ui="{ base: 'text-base sm:text-sm' }" />
                <USwitch v-model="onlyChanged" label="Only changed" />
              </div>
              <div v-for="group in groups" :key="group.letter" class="rule-group">
                <h3>{{ group.letter }} · {{ group.name }}</h3>
                <article
                  v-for="card in group.cards"
                  :id="`rule-${card.configKey}`"
                  :key="card.configKey"
                  class="rule-card"
                  :class="{ changed: cardChanged(card), highlighted: highlighted === card.configKey }"
                >
                  <div class="rule-card-head">
                    <USwitch
                      :model-value="valueOf(cardField(card, 'enabled')) === true"
                      :disabled="locked"
                      :aria-label="`Enable ${card.title}`"
                      @update:model-value="updateField(cardField(card, 'enabled'), $event)"
                    />
                    <div class="rule-card-title">
                      <strong>{{ card.title }}</strong>
                      <span class="rule-ids">
                        <NuxtLink v-for="rule in card.rules" :key="rule.id" :to="`/rules?rule=${encodeURIComponent(rule.id)}`" :title="`${rule.id}: ${rule.name}`"><code>{{ rule.id }}</code></NuxtLink>
                      </span>
                    </div>
                    <span v-if="cardChanged(card)" class="changed-badge">changed</span>
                  </div>
                  <p class="rule-card-description">{{ card.description }}</p>
                  <p v-for="(issue, index) in cardIssues(card)" :key="index" class="field-issue" :class="issue.level">{{ issue.message }}</p>
                  <details :open="isOpen(card)" @toggle="toggleCard(card, ($event.target as HTMLDetailsElement).open)">
                    <summary>Options</summary>
                    <ConfigField
                      v-for="field in cardOptions(card)"
                      :key="field.key"
                      :field="field"
                      :value="valueOf(field)"
                      :changed="changed(field)"
                      :issue="issueFor(field)"
                      :disabled="locked"
                      :unset-label="field.key === 'severity' ? severityLabel(card) : undefined"
                      @update="updateField(field, $event)"
                    />
                  </details>
                </article>
              </div>
              <p v-if="!groups.length" class="muted">No rules match.</p>
            </section>
          </fieldset>
        </div>

        <aside class="yaml-pane" :class="{ hidden: mobilePane !== 'yaml' }" aria-label="linti.yaml">
          <div class="yaml-toolbar">
            <UButton icon="i-lucide-download" size="sm" @click="downloadText('linti.yaml', configs.yaml.value, 'text/yaml')">Download linti.yaml</UButton>
            <UButton icon="i-lucide-square-terminal" size="sm" color="neutral" variant="outline" to="/playground">Try in playground</UButton>
            <UDropdownMenu :items="moreActions" :content="{ align: 'end' }">
              <UButton icon="i-lucide-ellipsis" size="sm" color="neutral" variant="ghost" aria-label="More YAML actions" />
            </UDropdownMenu>
            <input ref="fileInput" type="file" accept=".yaml,.yml,text/yaml" class="sr-only" aria-label="Open a linti.yaml file" @change="openFile($event.target as HTMLInputElement)">
          </div>
          <p v-if="shareError" class="error" role="alert">{{ shareError }}</p>
          <p class="yaml-summary" aria-live="polite">
            <span>{{ plural(changedCount, 'setting') }} changed from the defaults</span>
            <span v-if="errorCount" class="error">· {{ plural(errorCount, 'error') }}</span>
            <span v-if="warningCount" class="warning">· {{ plural(warningCount, 'warning') }}</span>
          </p>
          <CodeEditor ref="editor" class="editor" :model-value="yamlText" label="linti.yaml" language="yaml" wrap :diagnostics="diagnostics" @update:model-value="onType" />
          <ul v-if="parsed.parseErrors.length || issues.length" class="problems">
            <li v-for="(error, index) in parsed.parseErrors" :key="`p${index}`" class="error">{{ error.message }}</li>
            <li v-for="(issue, index) in issues" :key="`i${index}`" :class="issue.level">
              <button @click="focusIssue(issue)">{{ issue.message }}</button>
            </li>
          </ul>
          <p class="muted">Edits here are used by the <NuxtLink to="/playground">playground</NuxtLink> immediately. Save them above when you want to keep this version. A share link contains this YAML and opens as a local draft.</p>
        </aside>
      </div>
      <!-- Stacked layout: keeps saving within reach while editing far down. -->
      <div v-if="configs.dirty.value" class="save-bar">
        <span>Unsaved changes</span>
        <UButton size="sm" :loading="panel?.saving" @click="panel?.save()">{{ configs.activeProfile.value ? 'Save changes' : 'Save configuration' }}</UButton>
      </div>
    </div>
  </div>
</template>

<style scoped>
.lint-tool { container-type: inline-size; }
.configurator { margin-top: 0; }
.return-links { position: sticky; top: calc(var(--ui-header-height) + .5rem); z-index: 10; display: flex; flex-wrap: wrap; gap: .4rem; align-items: center; margin-bottom: 1.2rem; padding: .5rem; border: 1px solid var(--ui-border); border-radius: .5rem; background: var(--ui-bg); }
.pane-switch { display: none; }
.layout { display: grid; grid-template-columns: minmax(0, 1fr) minmax(18rem, 26rem); gap: 1.4rem; align-items: start; }
.form { min-width: 0; border: 0; padding: 0; margin: 0; }
.form-section + .form-section { margin-top: 1.6rem; }
.form-section h2 { font-size: 1.15rem; font-weight: 700; margin-bottom: .3rem; }
.limits { margin-top: .5rem; }
.limits summary, .rule-card summary { cursor: pointer; font-size: .85rem; font-weight: 600; color: var(--ui-text-muted); }
.rule-filters { display: flex; flex-wrap: wrap; align-items: center; gap: .8rem; margin: .5rem 0 1rem; }
.rule-group h3 { margin: 1.2rem 0 .5rem; font-size: .78rem; font-weight: 700; letter-spacing: .04em; text-transform: uppercase; color: var(--ui-text-muted); }
.rule-card { padding: .75rem .9rem; margin-bottom: .6rem; border: 1px solid var(--ui-border); border-radius: .55rem; background: var(--ui-bg); transition: box-shadow .3s; scroll-margin: calc(var(--ui-header-height) + 4rem); }
.rule-card.changed { border-left: 3px solid var(--ui-primary); }
.rule-card.highlighted { box-shadow: 0 0 0 3px color-mix(in srgb, var(--ui-primary) 45%, transparent); }
.rule-card-head { display: flex; align-items: center; gap: .6rem; }
.rule-card-title { display: flex; flex-wrap: wrap; align-items: baseline; gap: .2rem .5rem; flex: 1; min-width: 0; }
.rule-ids { display: flex; flex-wrap: wrap; gap: .3rem; }
.rule-ids a { font-size: .75rem; color: var(--ui-primary); }
@media (pointer: coarse) {
  /* A finger-sized target without making the card head taller. */
  .rule-ids a { display: inline-block; padding: .75rem .25rem; margin: -.75rem -.25rem; }
}
.rule-ids a:hover { text-decoration: underline; }
.rule-card-description { margin: .3rem 0 .4rem; font-size: .83rem; line-height: 1.4; color: var(--ui-text-muted); }
.banner { padding: .7rem .9rem; margin-bottom: 1rem; border-left: 3px solid var(--ui-error); background: var(--ui-bg-elevated); }
.save-bar { display: none; }
.yaml-pane { position: sticky; top: calc(var(--ui-header-height) + 1rem); display: flex; flex-direction: column; gap: .6rem; min-width: 0; }
.yaml-toolbar { display: flex; flex-wrap: wrap; gap: .35rem; }
.editor { --editor-height: min(60dvh, 34rem); }
.yaml-summary { display: flex; flex-wrap: wrap; gap: .3rem; font-size: .82rem; color: var(--ui-text-muted); }
.problems { list-style: none; margin: 0; padding: .5rem .7rem; border: 1px solid var(--ui-border); border-radius: .5rem; background: var(--ui-bg-elevated); font-size: .8rem; }
.problems li { padding: .25rem 0; border-left: 3px solid; padding-left: .5rem; margin: .2rem 0; overflow-wrap: anywhere; }
.problems li.error { border-color: var(--ui-error); }
.problems li.warning { border-color: var(--ui-warning); }
.problems button { text-align: left; }
.problems button:hover { text-decoration: underline; }
.field-issue { font-size: .8rem; margin-bottom: .3rem; }
/* The layout follows the space the page gives it, not the viewport: next to
   Docus' navigation a 1024px tablet leaves the form only ~160px otherwise. */
@container (max-width: 880px) {
  .layout { grid-template-columns: minmax(0, 1fr); }
  .pane-switch { display: flex; gap: .3rem; margin-bottom: 1rem; padding: .25rem; border: 1px solid var(--ui-border); border-radius: .55rem; }
  .pane-switch button { flex: 1; min-height: 2.5rem; padding: .45rem; border-radius: .4rem; font-weight: 600; font-size: .9rem; }
  .pane-switch button.active { background: var(--ui-primary); color: var(--ui-text-inverted); }
  .form-pane.hidden, .yaml-pane.hidden { display: none; }
  .yaml-pane { position: static; }
  .editor { --editor-height: 60dvh; }
  .return-links { position: static; }
  .save-bar { position: sticky; bottom: 0; z-index: 10; display: flex; align-items: center; justify-content: space-between; gap: .6rem; margin-top: 1rem; padding: .6rem .8rem calc(.6rem + env(safe-area-inset-bottom)); border: 1px solid var(--ui-border-accented); border-left: 3px solid var(--ui-warning); border-radius: .55rem; background: var(--ui-bg); box-shadow: 0 -.4rem 1.2rem rgb(0 0 0 / 8%); font-size: .88rem; font-weight: 600; }
}
</style>
