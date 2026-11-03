export type Finding = {
  /** Set by whole-process runs; a single-rule run lints one known procedure. */
  procedure?: string
  rule_id: string
  message: string
  line: number
  column: number
  severity: 'error' | 'warning'
  fixable: boolean
}

export type ProcessResult = {
  format: 'ti' | 'pa' | 'yaml'
  process_name: string
  code: string
  fixes: Record<string, number>
  issues: Finding[]
  warnings: string[]
}
export type RuleResult = { code: string, fixes: number, warnings: string[], issues: Finding[] }
export type ValidateResult = { valid: boolean, message?: string }

export type RuleContext = {
  config: string
  parameters: string[]
  variables: string[]
  datasource_type: string
  datasource_query: string
}

export type LintRequest =
  | { action: 'process', code: string, config: string, fix: boolean }
  | { action: 'rule', code: string, procedure: string, ruleId: string, fix: boolean, context: RuleContext }
  | { action: 'validate', config: string }

type ResultOf<R extends LintRequest> = R['action'] extends 'process'
  ? ProcessResult
  : R['action'] extends 'rule' ? RuleResult : ValidateResult

type WorkerReply = { id: number, status?: 'running', result?: unknown, error?: string }
type Job = { request: LintRequest, resolve: (result: unknown) => void }

// Downloading Pyodide can take a while; a lint run should not.
const LOAD_TIMEOUT_MS = 120_000
const RUN_TIMEOUT_MS = 15_000

/**
 * The LinTi worker behind a promise: `run()` resolves with the result, or with
 * null when the run failed (see `error`) or a newer request replaced it. One
 * request runs at a time and at most the latest one waits behind it.
 */
export function useLintiWorker() {
  const baseURL = useRuntimeConfig().app.baseURL
  const busy = ref(false)
  const ready = ref(false)
  const error = ref('')
  let worker: Worker | undefined
  let active: Job & { id: number } | undefined
  let queued: Job | undefined
  let nextId = 0
  let watchdog: ReturnType<typeof setTimeout> | undefined

  function stop(message = '') {
    clearTimeout(watchdog)
    worker?.terminate()
    worker = undefined
    active?.resolve(null)
    queued?.resolve(null)
    active = queued = undefined
    busy.value = ready.value = false
    error.value = message
  }

  function arm(ms: number) {
    clearTimeout(watchdog)
    watchdog = setTimeout(() => {
      const next = queued
      queued = undefined
      stop(ms === LOAD_TIMEOUT_MS
        ? 'LinTi could not finish loading. Please try again.'
        : `LinTi did not finish within ${RUN_TIMEOUT_MS / 1000} s and was stopped.`)
      if (next) start(next)
    }, ms)
  }

  function onMessage({ data }: MessageEvent<WorkerReply>) {
    if (!active || data.id !== active.id) return
    if (data.status === 'running') {
      ready.value = true
      arm(RUN_TIMEOUT_MS)
      return
    }
    clearTimeout(watchdog)
    const done = active
    const next = queued
    active = queued = undefined
    if (data.error) error.value = data.error
    done.resolve(data.error || next ? null : data.result)
    if (next) start(next)
    else busy.value = false
  }

  function start(job: Job) {
    active = { ...job, id: ++nextId }
    busy.value = true
    error.value = ''
    if (!worker) {
      worker = new Worker(`${baseURL}linti-worker.js`)
      worker.onmessage = onMessage
      worker.onerror = event => stop(event.message || 'The browser could not load Pyodide.')
    }
    arm(ready.value ? RUN_TIMEOUT_MS : LOAD_TIMEOUT_MS)
    worker.postMessage({ ...job.request, id: active.id })
  }

  function run<R extends LintRequest>(request: R): Promise<ResultOf<R> | null> {
    error.value = ''
    return new Promise((resolve) => {
      const job = { request, resolve: resolve as Job['resolve'] }
      if (!active) return start(job)
      queued?.resolve(null)
      queued = job
    })
  }

  onBeforeUnmount(() => stop())
  return { busy, ready, error, run }
}
