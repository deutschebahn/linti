import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { Module } from 'node:module'
import test from 'node:test'
import { build } from 'esbuild'
import { computed, effectScope, nextTick, reactive, ref, watch } from 'vue'

// Execute the component's real setup script with Vue's actual watcher scheduler.
// Only Nuxt navigation, lifecycle registration and the browser worker are stubbed.
const component = new URL('../app/components/RuleReference.vue', import.meta.url)
const source = await readFile(component, 'utf8')
const script = /<script setup lang="ts">([\s\S]*?)<\/script>/.exec(source)[1]
const imports = script.match(/^import .+$/gm).join('\n')
const body = script.replace(/^import .+$/gm, '')
const bundle = await build({
  stdin: {
    contents: `${imports}
      import { presets, presetText } from '../utils/lintiConfig'
      export function setupReference(hooks) {
        const { ref, computed, watch, nextTick, onMounted, onBeforeUnmount,
          useConfigLibrary, useConfirm, useRoute, useRouter, useState, useLintiWorker, navigateTo } = hooks
        ${body}
        return { selected, group, code, parameters, lintiYaml, usingWorkingConfig,
          openRuleInConfigurator, selectRule, useExampleSettings, run }
      }`,
    loader: 'ts',
    resolveDir: new URL('../app/components/', import.meta.url).pathname,
    sourcefile: component.pathname,
  },
  define: { 'import.meta.client': 'true' },
  bundle: true,
  format: 'cjs',
  platform: 'node',
  write: false,
})
const module = new Module('RuleReference.cjs')
module._compile(bundle.outputFiles[0].text, 'RuleReference.cjs')
const { setupReference } = module.exports

async function mountReference(t, query, { draft = ref(null), yaml = ref('') } = {}) {
  const scope = effectScope()
  const route = reactive({ query: { ...query } })
  const mounts = []
  const unmounts = []
  const requests = []
  const navigations = []
  const configs = {
    yaml,
    label: ref('Working configuration'),
    status: ref('draft'),
    dirty: ref(false),
    startDraft: (_name, text) => { yaml.value = text },
  }
  const worker = {
    busy: ref(false),
    error: ref(''),
    run: async (payload) => {
      requests.push(payload)
      return null
    },
  }
  const api = scope.run(() => setupReference({
    ref, computed, watch, nextTick,
    onMounted: callback => mounts.push(callback),
    onBeforeUnmount: callback => unmounts.push(callback),
    useConfigLibrary: () => configs,
    useConfirm: () => ({ ask: async () => true }),
    useRoute: () => route,
    useRouter: () => ({ replace: ({ query }) => { route.query = query } }),
    useState: () => draft,
    useLintiWorker: () => worker,
    navigateTo: target => navigations.push(target),
  }))
  t.after(() => scope.stop())
  for (const mount of mounts) await mount()
  await nextTick()
  return {
    api, route, requests, navigations,
    unmount() {
      for (const unmount of unmounts) unmount()
      scope.stop()
    },
  }
}

test('working-config deep links survive the selected-rule watcher', async (t) => {
  const yaml = ref('rules:\n  keyword_casing:\n    style: lowercase\n')
  for (const rule of ['F110', 'C150']) {
    const { api, requests } = await mountReference(t, { rule, config: 'working' }, { yaml })
    assert.equal(api.selected.value.id, rule)
    assert.equal(api.usingWorkingConfig.value, true)
    assert.equal(api.lintiYaml.value, yaml.value)
    api.run()
    assert.equal(requests.at(-1).ruleId, rule)
    assert.equal(requests.at(-1).context.config, yaml.value)
  }
})

test('configurator round trip restores code while using the edited working YAML', async (t) => {
  const draft = ref(null)
  const yaml = ref('')
  const first = await mountReference(t, { rule: 'F110' }, { draft, yaml })
  first.api.code.value = 'IF (x = 1);\nENDIF;'
  first.api.parameters.value = 'pFactor'
  first.api.openRuleInConfigurator()
  assert.deepEqual(first.navigations.at(-1), { path: '/config', query: { from: 'rules', rule: 'F110' }, hash: '#rule-keyword_casing' })
  first.unmount()

  // The configurator edits the shared YAML, then returns with config=working.
  yaml.value = 'rules:\n  keyword_casing:\n    style: lowercase\n'
  const { api, requests } = await mountReference(t, { rule: 'F110', config: 'working' }, { draft, yaml })
  assert.equal(api.code.value, 'IF (x = 1);\nENDIF;')
  assert.equal(api.parameters.value, 'pFactor')
  assert.equal(api.usingWorkingConfig.value, true)
  api.run()
  assert.equal(requests.at(-1).context.config, yaml.value)
  assert.deepEqual(requests.at(-1).context.parameters, ['pFactor'])
})

test('route changes keep their config mode and explicit rule selection returns to examples', async (t) => {
  const yaml = ref('rules:\n  keyword_casing:\n    style: lowercase\n')
  const { api, route } = await mountReference(t, { rule: 'C150' }, { yaml })
  route.query = { rule: 'F110', config: 'working' }
  await nextTick()
  assert.equal(api.selected.value.id, 'F110')
  assert.equal(api.usingWorkingConfig.value, true)
  assert.equal(api.lintiYaml.value, yaml.value)

  api.useExampleSettings()
  await nextTick()
  assert.equal(api.usingWorkingConfig.value, false)

  route.query = { rule: 'F110', config: 'working' }
  await nextTick()
  api.selectRule({ id: 'C150' })
  await nextTick()
  assert.equal(api.selected.value.id, 'C150')
  assert.equal(api.usingWorkingConfig.value, false)
  assert.equal(route.query.config, undefined)
})

test('each configurator visit carries the rule anchor without replacing working edits', async (t) => {
  const draft = ref(null)
  const yaml = ref('')
  for (let visit = 0; visit < 3; visit++) {
    const query = visit === 0 ? { rule: 'F110' } : { rule: 'F110', config: 'working' }
    const reference = await mountReference(t, query, { draft, yaml })
    const before = yaml.value
    reference.api.openRuleInConfigurator()
    assert.deepEqual(reference.navigations.at(-1), {
      path: '/config',
      query: { from: 'rules', rule: 'F110' },
      hash: '#rule-keyword_casing',
    })
    if (visit > 0) assert.equal(yaml.value, before)
    reference.unmount()
    yaml.value = `# Edit ${visit + 1}\nrules:\n  keyword_casing:\n    style: lowercase\n`
  }
})

test('clearing a deep-linked category keeps the next selected rule visible', async (t) => {
  const { api, route } = await mountReference(t, { group: 'F' })
  assert.equal(api.group.value, 'F')
  assert.equal(api.selected.value.group, 'F')

  api.group.value = 'all'
  await nextTick()
  assert.equal(route.query.group, undefined)
  api.selectRule({ id: 'C150' })
  await nextTick()
  assert.equal(api.group.value, 'all')
  assert.equal(api.selected.value.id, 'C150')

  api.group.value = 'F'
  await nextTick()
  assert.equal(route.query.group, 'F')
  assert.equal(api.selected.value.id, 'C150', 'filtering alone does not change the selected rule')
})

test('a rule outside the linked category clears the filter', async (t) => {
  const { api } = await mountReference(t, { group: 'F', rule: 'C150' })
  assert.equal(api.selected.value.id, 'C150')
  assert.equal(api.group.value, 'all')
})
