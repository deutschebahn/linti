export type ConfirmAction = {
  label: string
  value: string
  color?: 'primary' | 'error' | 'neutral'
  variant?: 'solid' | 'outline'
}
type ConfirmRequest = { message: string, actions: ConfirmAction[], resolve: (value: string | null) => void }

// Client-only: requests are created from clicks, route changes and storage events.
const pending = shallowRef<ConfirmRequest | null>(null)

/** One confirmation dialog (ConfirmDialog.vue) for all tool pages, instead of window.confirm(). */
export function useConfirm() {
  /** Resolves with the chosen action's value, or null when cancelled. */
  function choose(message: string, actions: ConfirmAction[]): Promise<string | null> {
    pending.value?.resolve(null)
    return new Promise(resolve => (pending.value = { message, actions, resolve }))
  }

  async function ask(message: string, confirmLabel = 'Replace', danger = false): Promise<boolean> {
    return await choose(message, [{ label: confirmLabel, value: 'confirm', color: danger ? 'error' : 'primary' }]) === 'confirm'
  }

  function answer(value: string | null) {
    const request = pending.value
    pending.value = null
    request?.resolve(value)
  }

  return { pending, choose, ask, answer }
}
