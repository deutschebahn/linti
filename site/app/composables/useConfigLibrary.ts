import type { Ref } from 'vue'
import type { Router } from 'vue-router'
import { decodeSharedConfig, emptyLibrary, encodeSharedConfig, LIBRARY_KEY, MAX_SHARE_LENGTH, parseLibrary, removeProfile, saveProfile, uniqueName } from '../utils/configLibrary'
import type { ConfigLibrary, SavedConfig } from '../utils/configLibrary'
import { presets, presetText } from '../utils/lintiConfig'

const defaultYaml = presetText(presets[0]!)

export function shareLink(name: string, yaml: string): string | null {
  const payload = encodeSharedConfig({ name, yaml })
  if (payload.length > MAX_SHARE_LENGTH) return null
  const { baseURL } = useRuntimeConfig().app
  return `${location.origin}${baseURL}config#config=${payload}`
}

const baseProfile = (library: ConfigLibrary) => library.profiles.find(profile => profile.id === library.draft.baseId) ?? null
const isDefault = (library: ConfigLibrary) => !baseProfile(library) && !library.draft.name
  && (library.draft.yaml === defaultYaml || !library.draft.yaml.trim())
/** The draft differs from the profile it came from, or from LinTi's defaults. */
function isDirty(library: ConfigLibrary): boolean {
  const base = baseProfile(library)
  return base ? base.yaml !== library.draft.yaml : !isDefault(library)
}

let sync: { importHash: (hash: string) => void } | null = null

/**
 * Loads the library once per page load and writes every change back. Tabs
 * share it through storage events: another tab's save replaces the profiles
 * here, while each tab keeps its own draft, so the last write wins.
 */
function startSync(library: Ref<ConfigLibrary>, loaded: Ref<boolean>, storageError: Ref<boolean>, router: Router) {
  if (!loaded.value) {
    try {
      const stored = localStorage.getItem(LIBRARY_KEY)
      const parsed = parseLibrary(stored)
      if (parsed) library.value = parsed
      else if (stored) storageError.value = true
    } catch {
      storageError.value = true
    }
    loaded.value = true
  }
  // The state as last written or adopted, which needs no write.
  let written = JSON.stringify(library.value)

  function persist(value: ConfigLibrary) {
    const text = JSON.stringify(value)
    if (text === written) return
    try {
      localStorage.setItem(LIBRARY_KEY, text)
      written = text
      storageError.value = false
    } catch {
      storageError.value = true
    }
  }

  window.addEventListener('storage', (event) => {
    if (event.key !== LIBRARY_KEY || event.storageArea !== localStorage) return
    const stored = parseLibrary(event.newValue)
    if (!stored) return
    const next = { ...stored, draft: library.value.draft }
    written = JSON.stringify(next)
    library.value = next
  })

  // Mounting and the route watcher can both see one link; ask only once.
  let handledHash = ''
  function importHash(hash: string) {
    if (!hash.startsWith('#config=')) {
      handledHash = ''
      return
    }
    if (hash === handledHash) return
    handledHash = hash
    const shared = decodeSharedConfig(hash)
    const route = router.currentRoute.value
    void router.replace({ path: route.path, query: route.query, hash: '' })
    if (!shared) return
    const apply = () => (library.value.draft = { yaml: shared.yaml, baseId: null, name: shared.name })
    if (!isDirty(library.value) || library.value.draft.yaml === shared.yaml) apply()
    else void useConfirm().ask(`Replace the current unsaved configuration with the shared "${shared.name}"?`).then(ok => ok && apply())
  }

  effectScope(true).run(() => {
    watch(library, persist, { deep: true })
    // Pasting a share link into an open page only changes the fragment, which
    // the router picks up from popstate without remounting anything.
    watch(() => router.currentRoute.value.hash, importHash)
  })
  return { importHash }
}

/** Browser-only profile library, shared across all three interactive pages. */
export function useConfigLibrary() {
  const library = useState<ConfigLibrary>('linti-config-library', () => emptyLibrary(defaultYaml))
  const loaded = useState('linti-config-library-loaded', () => false)
  const storageError = useState('linti-config-library-storage-error', () => false)
  const route = useRoute()
  const router = useRouter()

  const activeProfile = computed(() => baseProfile(library.value))
  const yaml = computed({
    get: () => library.value.draft.yaml,
    set: (value: string) => { library.value.draft.yaml = value },
  })
  const dirty = computed(() => isDirty(library.value))
  const label = computed(() => activeProfile.value?.name ?? (isDefault(library.value) ? 'LinTi defaults' : library.value.draft.name || 'Local draft'))
  const status = computed(() => isDefault(library.value) ? 'defaults' : dirty.value ? 'draft' : 'saved')

  onMounted(() => {
    sync ??= startSync(library, loaded, storageError, router)
    // Nuxt may have consumed location.hash for anchor handling already.
    sync.importHash(route.hash)
  })

  function selectProfile(id: string) {
    const profile = library.value.profiles.find(item => item.id === id)
    if (profile) library.value.draft = { yaml: profile.yaml, baseId: id, name: profile.name }
  }

  function selectDefaults() {
    library.value.draft = { yaml: defaultYaml, baseId: null, name: '' }
  }

  function startDraft(name = '', source = yaml.value) {
    library.value.draft = { yaml: source, baseId: null, name }
  }

  /** Drop unsaved edits: back to the active profile, or to the defaults. */
  function discardDraft() {
    if (activeProfile.value) selectProfile(activeProfile.value.id)
    else selectDefaults()
  }

  function save(name: string, asNew = false): SavedConfig {
    library.value = saveProfile(library.value, name, crypto.randomUUID(), new Date().toISOString(), asNew)
    return activeProfile.value!
  }

  function deleteProfile(id: string) {
    library.value = removeProfile(library.value, id, defaultYaml)
  }

  /** The name, or a free variant of it such as `name (2)`. */
  function availableName(preferred: string): string {
    return uniqueName(library.value.profiles.map(profile => profile.name), preferred)
  }

  function importLibrary(raw: string): boolean {
    const imported = parseLibrary(raw)
    if (!imported) return false
    // Imported IDs must not collide with existing profiles.
    for (const profile of imported.profiles) {
      library.value.profiles.push({ ...profile, id: crypto.randomUUID(), name: availableName(profile.name) })
    }
    return true
  }

  return { library, yaml, loaded, storageError, activeProfile, dirty, label, status, selectProfile, selectDefaults, startDraft, discardDraft, save, deleteProfile, availableName, importLibrary }
}
