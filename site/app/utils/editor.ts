/** A place in the editor: a character range, or a 1-based line and column from LinTi. */
export type EditorTarget = { from: number, to: number } | { line: number, column: number }

export type EditorDiagnostic = EditorTarget & { severity: 'error' | 'warning', message: string, source?: string }

export type EditorKey = { key: string, run: () => void }

/** What CodeEditor.vue exposes to its parent through a template ref. */
export type CodeEditorHandle = {
  reveal: (target: EditorTarget) => void
  measure: () => void
}
