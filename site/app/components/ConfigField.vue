<script setup lang="ts">
/** One linti.yaml setting, rendered from its schema by ConfigConfigurator. */
const props = defineProps<{
  field: FieldSpec
  value: unknown
  changed: boolean
  disabled?: boolean
  /** Label for "not set" on nullable fields, e.g. the rule's own severity. */
  unsetLabel?: string
  issue?: ConfigIssue
}>()
const emit = defineEmits<{ update: [value: unknown] }>()

// USelect cannot hold null, so "not set" gets a sentinel value.
const UNSET = '__unset__'
const id = computed(() => `cfg-${props.field.path.join('-')}`)
const selectItems = computed(() => [
  ...(props.field.nullable ? [{ label: props.unsetLabel ?? 'Not set', value: UNSET }] : []),
  ...props.field.options.map(option => ({ label: option, value: option })),
])
const selectValue = computed(() => (props.value === null || props.value === undefined ? UNSET : String(props.value)))
// Descriptions come from the Python field docs, which quote names in backticks.
const descriptionParts = computed(() => props.field.description.split(/`([^`]+)`/))
const listValue = computed(() => (Array.isArray(props.value) ? props.value.map(String) : []))
// 16px text on phones keeps iOS Safari from zooming in when a field gets focus.
const fieldUi = { base: 'text-base sm:text-sm' }

function onSelect(value: unknown) {
  emit('update', value === UNSET ? null : value)
}

function onInteger(raw: string | number) {
  const number = Number(raw)
  if (String(raw).trim() !== '' && Number.isInteger(number)) emit('update', number)
}
</script>

<template>
  <div class="config-field" :class="{ changed, invalid: issue?.level === 'error' }">
    <div class="field-head">
      <USwitch
        v-if="field.kind === 'boolean'"
        :id="id"
        :model-value="value === true"
        :disabled="disabled"
        :label="field.label"
        @update:model-value="emit('update', $event)"
      />
      <label v-else class="field-label" :for="id">{{ field.label }}</label>
      <code class="field-key">{{ field.key }}</code>
      <span v-if="changed" class="changed-badge">changed</span>
      <UButton
        v-if="changed"
        size="sm"
        color="neutral"
        variant="ghost"
        icon="i-lucide-rotate-ccw"
        :disabled="disabled"
        :aria-label="`Reset ${field.key} to its default`"
        @click="emit('update', field.default)"
      />
    </div>
    <USelect
      v-if="field.kind === 'enum'"
      :id="id"
      :model-value="selectValue"
      :items="selectItems"
      :disabled="disabled"
      class="w-56 max-w-full"
      :ui="fieldUi"
      @update:model-value="onSelect"
    />
    <UInput
      v-else-if="field.kind === 'integer'"
      :id="id"
      type="number"
      step="1"
      :model-value="typeof value === 'number' ? String(value) : ''"
      :disabled="disabled"
      class="w-40 max-w-full"
      :ui="fieldUi"
      @update:model-value="onInteger"
    />
    <UInputTags
      v-else-if="field.kind === 'list'"
      :id="id"
      :model-value="listValue"
      :disabled="disabled"
      placeholder="Type and press Enter"
      class="w-full"
      :ui="fieldUi"
      @update:model-value="emit('update', $event)"
    />
    <UInput
      v-else-if="field.kind === 'string'"
      :id="id"
      :model-value="typeof value === 'string' ? value : ''"
      :disabled="disabled"
      class="w-full"
      :ui="fieldUi"
      @update:model-value="emit('update', $event)"
    />
    <p v-if="field.description" class="field-description">
      <template v-for="(part, index) in descriptionParts" :key="index">
        <code v-if="index % 2">{{ part }}</code><template v-else>{{ part }}</template>
      </template>
    </p>
    <p v-if="issue" class="field-issue" :class="issue.level" role="status">{{ issue.message }}</p>
  </div>
</template>

<style scoped>
.config-field { padding: .55rem 0; }
.field-head { display: flex; flex-wrap: wrap; align-items: center; gap: .4rem; margin-bottom: .3rem; }
.field-label { font-size: .88rem; font-weight: 650; }
.field-key { font-size: .72rem; color: var(--ui-text-muted); }
.field-description { margin-top: .25rem; font-size: .8rem; line-height: 1.4; color: var(--ui-text-muted); }
.field-description code { font-size: .75rem; }
.field-issue { margin-top: .25rem; font-size: .8rem; overflow-wrap: anywhere; }
.field-issue.error { color: var(--ui-error); }
.field-issue.warning { color: var(--ui-warning); }
@media (pointer: coarse) {
  .field-head :deep(button[aria-label^="Reset"]) { min-width: 2.75rem; min-height: 2.75rem; justify-content: center; }
}
</style>
