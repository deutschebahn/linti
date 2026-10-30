<script setup lang="ts">
/**
 * The configurator's profile library: pick, create, save, rename, duplicate,
 * delete, export and import configurations. It only changes the shared
 * library; ConfigConfigurator follows `configs.yaml`.
 */
import { nameProblem } from '../utils/configLibrary'

type NameMode = 'new' | 'duplicate' | 'rename'

const configs = useConfigLibrary()
const { ask, choose } = useConfirm()
const validator = useLintiWorker()
const profileError = ref('')
const libraryInput = ref<HTMLInputElement | null>(null)
const nameOpen = ref(false)
const nameMode = ref<NameMode>('new')
const nameValue = ref('')
const nameError = ref('')
const newTemplate = ref(presets[0]!.key)

const nameTitles: Record<NameMode, [title: string, submit: string]> = {
  new: ['New configuration', 'Create'],
  duplicate: ['Duplicate configuration', 'Duplicate'],
  rename: ['Rename configuration', 'Rename'],
}
const switcherValue = computed(() => configs.status.value === 'draft'
  ? 'draft'
  : configs.activeProfile.value ? `profile:${configs.activeProfile.value.id}` : 'defaults')

/** Validate with LinTi itself, then save; resolves whether it was saved. */
async function save(explicitName?: string, asNew = false): Promise<boolean> {
  if (validator.busy.value) return false
  const { draft } = configs.library.value
  const before = JSON.stringify(draft)
  const name = explicitName ?? (configs.activeProfile.value?.name || configs.availableName(draft.name.trim() || 'My configuration'))
  profileError.value = ''
  const result = await validator.run({ action: 'validate', config: draft.yaml })
  if (!result) {
    profileError.value = validator.error.value || 'LinTi could not validate this YAML.'
    return false
  }
  if (JSON.stringify(configs.library.value.draft) !== before) {
    profileError.value = 'The configuration changed during validation. Please save again.'
    return false
  }
  if (!result.valid) {
    profileError.value = result.message || 'LinTi could not load this YAML.'
    return false
  }
  try {
    configs.save(name, asNew)
    return true
  } catch (error) {
    profileError.value = (error as Error).message
    return false
  }
}

/** Run *action* once unsaved changes are saved or discarded, if there are any. */
async function guard(action: () => void) {
  if (!configs.dirty.value) return action()
  const choice = await choose('There are unsaved changes. Save them before switching?', [
    { label: 'Discard changes', value: 'discard', color: 'neutral', variant: 'outline' },
    { label: 'Save', value: 'save' },
  ])
  if (choice === 'discard') configs.discardDraft()
  if (choice === 'discard' || (choice === 'save' && await save())) action()
}

function switchTo(select: HTMLSelectElement) {
  const value = select.value
  // Stay on the current entry until any unsaved changes are dealt with.
  select.value = switcherValue.value
  if (value === switcherValue.value) return
  void guard(() => {
    profileError.value = ''
    if (value === 'defaults') configs.selectDefaults()
    else configs.selectProfile(value.replace(/^profile:/, ''))
  })
}

function openNameDialog(mode: NameMode) {
  nameMode.value = mode
  newTemplate.value = presets[0]!.key
  nameValue.value = mode === 'new' ? '' : mode === 'duplicate' ? `${configs.label.value} copy` : configs.activeProfile.value?.name ?? ''
  nameError.value = ''
  nameOpen.value = true
}

function submitName() {
  const renaming = nameMode.value === 'rename'
  nameError.value = nameProblem(configs.library.value, nameValue.value, renaming ? configs.activeProfile.value?.id : null) ?? ''
  if (nameError.value) return
  nameOpen.value = false
  const name = nameValue.value.trim()
  if (nameMode.value === 'new') {
    const preset = presets.find(item => item.key === newTemplate.value) ?? presets[0]!
    configs.startDraft(name, presetText(preset))
  } else {
    void save(name, nameMode.value === 'duplicate')
  }
}

async function deleteActive() {
  const profile = configs.activeProfile.value
  if (!profile || !(await ask(`Delete "${profile.name}" from this browser? Any unsaved edits to it will also be discarded.`, 'Delete', true))) return
  configs.deleteProfile(profile.id)
}

function exportLibrary() {
  const backup = { version: 1, profiles: configs.library.value.profiles, draft: { yaml: '', baseId: null, name: '' } }
  downloadText('linti-configurations.json', JSON.stringify(backup, null, 2), 'application/json')
}

async function importLibrary(input: HTMLInputElement) {
  const file = input.files?.[0]
  input.value = ''
  if (file) profileError.value = configs.importLibrary(await file.text()) ? '' : 'This is not a LinTi configuration library.'
}

defineExpose({ save, guard, saving: validator.busy })
</script>

<template>
  <section class="library-panel" aria-label="Current configuration">
    <div class="library-title">
      <h2>Current configuration</h2>
      <span class="status-badge" :class="configs.status.value">{{ configs.dirty.value ? 'Unsaved changes' : configs.status.value === 'saved' ? 'Saved in this browser' : 'LinTi defaults' }}</span>
    </div>
    <p class="muted intro">{{ configs.status.value === 'defaults' ? 'Create a configuration with + or adjust a rule below, then save it.' : 'Adjust the rules below. Save when you want to keep this version.' }}</p>
    <p v-if="configs.storageError.value" class="error" role="alert">Browser storage is unavailable. Download your YAML before leaving this page.</p>
    <div class="library-primary">
      <div class="config-switcher">
        <label class="switcher-label">Use configuration
          <!-- Native select: the phone's own picker is the most usable one there. -->
          <select :value="switcherValue" @change="switchTo($event.target as HTMLSelectElement)">
            <option value="defaults">LinTi defaults</option>
            <option v-if="configs.status.value === 'draft'" value="draft">{{ configs.label.value }} (draft)</option>
            <option v-for="profile in configs.library.value.profiles" :key="profile.id" :value="`profile:${profile.id}`">{{ profile.name }}</option>
          </select>
        </label>
        <UButton icon="i-lucide-plus" color="neutral" variant="outline" size="sm" aria-label="Create empty configuration" title="New configuration" @click="guard(() => openNameDialog('new'))" />
        <UButton v-if="configs.activeProfile.value" icon="i-lucide-trash-2" color="error" variant="ghost" size="sm" aria-label="Delete selected configuration" title="Delete selected configuration" @click="deleteActive()" />
      </div>
      <UButton v-if="configs.dirty.value" class="save-action" size="sm" :loading="validator.busy.value" @click="save()">{{ configs.activeProfile.value ? 'Save changes' : 'Save configuration' }}</UButton>
    </div>
    <p class="local-note">Only in this browser · no account or sync</p>
    <p v-if="profileError" class="error" role="alert">{{ profileError }}</p>
    <details class="library-more">
      <summary>Manage configurations</summary>
      <p class="muted">Profiles stay in this browser only. Clearing its data removes them; export a copy to keep them elsewhere.</p>
      <div v-if="configs.activeProfile.value" class="library-actions">
        <UButton size="sm" color="neutral" variant="outline" @click="openNameDialog('duplicate')">Duplicate current</UButton>
        <UButton size="sm" color="neutral" variant="outline" @click="openNameDialog('rename')">Rename</UButton>
      </div>
      <div class="library-actions">
        <UButton size="sm" color="neutral" variant="ghost" @click="exportLibrary()">Export saved profiles</UButton>
        <UButton size="sm" color="neutral" variant="ghost" @click="libraryInput?.click()">Import profiles</UButton>
        <input ref="libraryInput" type="file" accept=".json,application/json" class="sr-only" aria-label="Import configuration backup" @change="importLibrary($event.target as HTMLInputElement)">
      </div>
    </details>

    <UModal v-model:open="nameOpen" :title="nameTitles[nameMode][0]" :description="nameMode === 'new' ? 'Choose a starting point. You can change every setting before saving.' : undefined" :close="false">
      <template #body>
        <form id="config-name-form" class="name-form" @submit.prevent="submitName()">
          <UFormField label="Configuration name" :error="nameError || undefined">
            <UInput v-model="nameValue" maxlength="100" placeholder="e.g. Strict CI" class="w-full" :ui="{ base: 'text-base sm:text-sm' }" @update:model-value="nameError = ''" />
          </UFormField>
          <fieldset v-if="nameMode === 'new'" class="template-options">
            <legend>Start from</legend>
            <label v-for="preset in presets" :key="preset.key" class="template-option">
              <input v-model="newTemplate" type="radio" name="new-template" :value="preset.key">
              <span><strong>{{ preset.title }}</strong><small>{{ preset.description }}</small></span>
            </label>
          </fieldset>
        </form>
      </template>
      <template #footer>
        <div class="name-buttons">
          <UButton type="button" size="sm" color="neutral" variant="ghost" @click="nameOpen = false">Cancel</UButton>
          <UButton type="submit" form="config-name-form" size="sm">{{ nameTitles[nameMode][1] }}</UButton>
        </div>
      </template>
    </UModal>
  </section>
</template>

<style scoped>
.library-panel { min-width: 0; padding: .85rem 1rem; margin-bottom: 1.2rem; border: 1px solid var(--ui-border-accented); border-radius: .6rem; background: var(--ui-bg-elevated); }
.library-title, .library-actions { display: flex; gap: .55rem; align-items: center; flex-wrap: wrap; }
.library-title h2 { font-size: 1.1rem; font-weight: 700; }
.intro { margin: .25rem 0 .7rem; }
.status-badge { border: 1px solid var(--ui-border); border-radius: 1rem; padding: .2rem .6rem; font-size: .75rem; white-space: nowrap; }
.status-badge.draft { border-color: var(--ui-warning); }
.status-badge.saved { border-color: var(--ui-success); }
.library-primary { display: flex; flex-wrap: wrap; gap: .6rem; align-items: end; }
.config-switcher { display: flex; flex: 1 1 14rem; gap: .25rem; align-items: end; min-width: 0; }
.switcher-label { display: flex; flex: 1; flex-direction: column; gap: .2rem; min-width: 0; margin-right: .2rem; font-size: .8rem; font-weight: 650; }
.switcher-label select { box-sizing: border-box; width: 100%; min-width: 0; padding: .35rem .5rem; border: 1px solid var(--ui-border); border-radius: .4rem; color: var(--ui-text); background: var(--ui-bg); font-size: 1rem; }
.local-note { margin: .5rem 0 0; color: var(--ui-text-muted); font-size: .76rem; }
.library-more { margin-top: .75rem; padding-top: .6rem; border-top: 1px solid var(--ui-border); }
.library-more summary { width: fit-content; cursor: pointer; color: var(--ui-primary); font-size: .82rem; font-weight: 600; }
.library-more .muted { margin: .5rem 0; }
.library-actions { margin: .55rem 0; }
.name-form { display: grid; gap: .8rem; }
.name-buttons { display: flex; flex: 1; flex-wrap: wrap; justify-content: flex-end; gap: .5rem; }
.template-options { min-width: 0; padding: 0; border: 0; }
.template-options legend { margin-bottom: .4rem; font-size: .8rem; font-weight: 650; }
.template-option { display: flex; gap: .7rem; align-items: start; padding: .55rem .65rem; border: 1px solid var(--ui-border); border-radius: .45rem; cursor: pointer; }
.template-option + .template-option { margin-top: .4rem; }
.template-option:has(input:checked) { border-color: var(--ui-primary); background: color-mix(in srgb, var(--ui-primary) 6%, var(--ui-bg)); }
.template-option input { margin-top: .2rem; accent-color: var(--ui-primary); }
.template-option span { display: grid; gap: .15rem; min-width: 0; }
.template-option strong { font-size: .9rem; }
.template-option small { color: var(--ui-text-muted); font-size: .76rem; line-height: 1.35; }
/* On narrow layouts the configurator's sticky save bar takes over. */
@container (max-width: 880px) {
  .save-action { display: none; }
}
@media (pointer: coarse) {
  .switcher-label select { min-height: 2.75rem; }
  .config-switcher :deep(button) { min-width: 2.75rem; min-height: 2.75rem; justify-content: center; }
}
</style>
