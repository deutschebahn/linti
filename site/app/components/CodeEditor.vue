<script setup lang="ts">
/**
 * CodeMirror behind v-model. `update:modelValue` fires for the visitor's own
 * edits; a new `modelValue` from the parent replaces the text without one.
 * Diagnostics resolve against the text as it is when they arrive.
 */
import type { EditorView } from '@codemirror/view'
import type { AnnotationType } from '@codemirror/state'
import type { setDiagnostics as SetDiagnostics } from '@codemirror/lint'
import type { CodeEditorHandle, EditorDiagnostic, EditorKey, EditorTarget } from '../utils/editor'

const props = withDefaults(defineProps<{
  modelValue: string
  label: string
  language?: 'yaml'
  wrap?: boolean
  diagnostics?: EditorDiagnostic[]
  keys?: EditorKey[]
}>(), { language: undefined, diagnostics: () => [], keys: () => [] })
const emit = defineEmits<{ 'update:modelValue': [value: string] }>()

const host = ref<HTMLElement | null>(null)
let view: EditorView | undefined
let setDiagnostics: typeof SetDiagnostics | undefined
// Marks text replaced from modelValue, which must not be echoed back.
let external: AnnotationType<boolean> | undefined

function rangeOf(target: EditorTarget) {
  const doc = view!.state.doc
  if ('from' in target) {
    const from = Math.min(Math.max(target.from, 0), doc.length)
    return { from, to: Math.min(Math.max(target.to, from), doc.length) }
  }
  const line = doc.line(Math.min(Math.max(target.line, 1), doc.lines))
  const from = Math.min(line.from + Math.max(target.column, 1) - 1, line.to)
  const word = /^\w+/.exec(doc.sliceString(from, line.to))
  return { from, to: word ? from + word[0].length : Math.min(from + 1, line.to) }
}

function pushDiagnostics() {
  if (!view || !setDiagnostics) return
  const diagnostics = props.diagnostics.map(item => ({ ...rangeOf(item), severity: item.severity, message: item.message, source: item.source }))
  view.dispatch(setDiagnostics(view.state, diagnostics))
}

function reveal(target: EditorTarget) {
  if (!view) return
  const { from, to } = rangeOf(target)
  view.dispatch({ selection: { anchor: from, head: to }, scrollIntoView: true })
  // On touch screens focusing would open the keyboard over the code.
  if (matchMedia('(pointer: fine)').matches) view.focus()
  else host.value?.scrollIntoView({ behavior: 'smooth', block: 'center' })
}

defineExpose<CodeEditorHandle>({ reveal, measure: () => view?.requestMeasure() })

// The text first, so diagnostics arriving with it resolve against it.
watch(() => props.modelValue, (text) => {
  if (view && text !== view.state.doc.toString()) {
    view.dispatch({ changes: { from: 0, to: view.state.doc.length, insert: text }, annotations: external!.of(true) })
  }
})
watch(() => props.diagnostics, pushDiagnostics)

onMounted(async () => {
  const [{ EditorView, keymap, lineNumbers, highlightActiveLine, highlightActiveLineGutter, drawSelection }, { EditorState, Annotation }, commands, lint] = await Promise.all([
    import('@codemirror/view'),
    import('@codemirror/state'),
    import('@codemirror/commands'),
    import('@codemirror/lint'),
  ])
  const language = props.language === 'yaml' ? await yamlSupport() : []
  setDiagnostics = lint.setDiagnostics
  external = Annotation.define<boolean>()
  view = new EditorView({
    parent: host.value!,
    state: EditorState.create({
      // Read now: the text can change while the modules load.
      doc: props.modelValue,
      extensions: [
        lineNumbers(),
        highlightActiveLineGutter(),
        highlightActiveLine(),
        drawSelection(),
        props.wrap ? EditorView.lineWrapping : [],
        commands.history(),
        lint.lintGutter(),
        language,
        keymap.of([
          ...props.keys.map(({ key, run }) => ({ key, run: () => (run(), true) })),
          ...commands.defaultKeymap,
          ...commands.historyKeymap,
          commands.indentWithTab,
        ]),
        EditorView.updateListener.of((update) => {
          if (update.docChanged && !update.transactions.some(tr => tr.annotation(external!))) {
            emit('update:modelValue', update.state.doc.toString())
          }
        }),
        EditorView.contentAttributes.of({ 'aria-label': props.label }),
      ],
    }),
  })
  pushDiagnostics()
})

async function yamlSupport() {
  const [{ yaml }, { HighlightStyle, syntaxHighlighting }, { tags }] = await Promise.all([
    import('@codemirror/lang-yaml'),
    import('@codemirror/language'),
    import('@lezer/highlight'),
  ])
  // Theme colors instead of a fixed palette, so light and dark mode both read well.
  const highlight = HighlightStyle.define([
    { tag: [tags.propertyName, tags.definition(tags.propertyName)], color: 'var(--ui-primary)' },
    { tag: tags.comment, color: 'var(--ui-text-muted)', fontStyle: 'italic' },
    { tag: [tags.string, tags.special(tags.string), tags.content], color: 'var(--ui-info)' },
    { tag: [tags.bool, tags.number, tags.null, tags.keyword, tags.atom], color: 'var(--ui-warning)' },
    { tag: [tags.punctuation, tags.separator, tags.squareBracket, tags.brace], color: 'var(--ui-text-muted)' },
  ])
  return [yaml(), syntaxHighlighting(highlight)]
}

onBeforeUnmount(() => view?.destroy())
</script>

<template>
  <!-- The parent sizes the editor through --editor-height. -->
  <div ref="host" class="code-editor" />
</template>

<style scoped>
.code-editor { border: 1px solid var(--ui-border); border-radius: .5rem; overflow: hidden; background: var(--ui-bg); }
.code-editor :deep(.cm-editor) { height: var(--editor-height, 20rem); font-size: .85rem; }
.code-editor :deep(.cm-editor.cm-focused) { outline: 2px solid var(--ui-primary); outline-offset: -1px; }
.code-editor :deep(.cm-scroller) { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; line-height: 1.5; }
.code-editor :deep(.cm-content) { caret-color: var(--ui-text); }
.code-editor :deep(.cm-gutters) { background: var(--ui-bg-elevated); color: var(--ui-text-muted); border-right: 1px solid var(--ui-border); }
.code-editor :deep(.cm-activeLine), .code-editor :deep(.cm-activeLineGutter) { background: color-mix(in srgb, var(--ui-primary) 7%, transparent); }
.code-editor :deep(.cm-selectionBackground), .code-editor :deep(.cm-focused .cm-selectionBackground) { background: color-mix(in srgb, var(--ui-primary) 25%, transparent) !important; }
.code-editor :deep(.cm-tooltip) { background: var(--ui-bg-elevated); color: var(--ui-text); border: 1px solid var(--ui-border); }
@media (max-width: 860px) {
  /* 16px text on phones keeps iOS Safari from zooming in when the editor gets focus. */
  .code-editor :deep(.cm-editor) { font-size: 1rem; }
}
</style>
