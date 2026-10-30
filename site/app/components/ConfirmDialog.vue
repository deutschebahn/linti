<script setup lang="ts">
const { pending, answer } = useConfirm()
// Keeps the text in place while the dialog animates closed.
const shown = shallowRef(pending.value)
watch(pending, request => request && (shown.value = request))
</script>

<template>
  <UModal :open="!!pending" :title="shown?.message" :ui="{ footer: 'flex-wrap justify-end gap-2' }" @update:open="open => open || answer(null)">
    <template #footer>
      <UButton color="neutral" variant="ghost" @click="answer(null)">Cancel</UButton>
      <UButton
        v-for="action in shown?.actions"
        :key="action.value"
        :color="action.color ?? 'primary'"
        :variant="action.variant ?? 'solid'"
        @click="answer(action.value)"
      >
        {{ action.label }}
      </UButton>
    </template>
  </UModal>
</template>
