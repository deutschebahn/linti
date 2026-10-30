import assert from 'node:assert/strict'
import test from 'node:test'
import { Module } from 'node:module'
import { build } from 'esbuild'

// Bundle the same TS utility, JSON schema and YAML parser that Nuxt loads.
const bundle = await build({
  entryPoints: [new URL('../app/utils/lintiConfig.ts', import.meta.url).pathname],
  bundle: true,
  format: 'cjs',
  platform: 'node',
  write: false,
})
const module = new Module('lintiConfig.cjs')
module._compile(bundle.outputFiles[0].text, 'lintiConfig.cjs')
const { effectiveValue, isChanged, parseConfig, ruleCards, setOption, stringifyConfig, topLevelFields, validateConfig } = module.exports

test('coerced values render like Core values and are not flagged as invalid', () => {
  const enabled = ruleCards.find(card => card.configKey === 'keyword_casing').fields.find(field => field.key === 'enabled')
  const depth = topLevelFields.find(field => field.key === 'max_nesting_depth')
  const data = parseConfig('rules:\n  keyword_casing:\n    enabled: "false"\nmax_nesting_depth: "2"\n').data
  assert.equal(effectiveValue(data, enabled), false)
  assert.equal(effectiveValue(data, depth), 2)
  assert.ok(!validateConfig(data).some(issue => issue.level === 'error'))
  assert.equal(isChanged(data, depth), 2 !== depth.default)
})

test('local feedback still catches invalid forms before authoritative Core save', () => {
  const data = parseConfig('rules:\n  keyword_casing:\n    enabled: maybe\n').data
  assert.ok(validateConfig(data).some(issue => issue.path.join('.') === 'rules.keyword_casing.enabled' && issue.level === 'error'))
})

test('YAML integers use Core semantics and survive unrelated form edits', () => {
  const depth = topLevelFields.find(field => field.key === 'max_nesting_depth')
  for (const directive of ['', '%YAML 1.2\n---\n']) {
    const { doc, data, parseErrors } = parseConfig(`${directive}# Keep this comment\nmax_nesting_depth: 010\n`)
    assert.deepEqual(parseErrors, [])
    assert.equal(effectiveValue(data, depth), 8)
    setOption(doc, ['target_version'], 'v12', null)
    const text = stringifyConfig(doc)
    assert.match(text, /# Keep this comment/)
    assert.equal(parseConfig(text).data.max_nesting_depth, 8)
  }
  // Quoted numbers are decimal strings for pydantic; invalid octal is a string.
  assert.equal(effectiveValue(parseConfig('max_nesting_depth: "010"\n').data, depth), 10)
  assert.deepEqual(parseConfig('generic_prefixes: [08, 09, y, Y, n, N]\n').data.generic_prefixes, ['08', '09', 'y', 'Y', 'n', 'N'])
})

test('YAML booleans match Core and cannot silently become string-list entries', () => {
  const values = ['on', 'On', 'ON', 'yes', 'Yes', 'YES', 'true', 'True', 'TRUE',
    'off', 'Off', 'OFF', 'no', 'No', 'NO', 'false', 'False', 'FALSE']
  const { data } = parseConfig(`generic_prefixes: [${values.join(', ')}]\n`)
  assert.deepEqual(data.generic_prefixes, [...Array(9).fill(true), ...Array(9).fill(false)])
  assert.ok(validateConfig(data).some(issue => issue.path.join('.') === 'generic_prefixes' && issue.level === 'error'))
})

test('form-created strings retain their type through YAML serialization', () => {
  const values = ['on', 'off', 'yes', 'no', 'true', 'false', '010', '08', 'y', 'n', '2026-10-04']
  const { doc } = parseConfig('')
  setOption(doc, ['generic_prefixes'], values, [])
  setOption(doc, ['rules', 'docstring_region', 'region_name'], 'on', 'Docstring')
  const { data, parseErrors } = parseConfig(stringifyConfig(doc))
  assert.deepEqual(parseErrors, [])
  assert.deepEqual(data.generic_prefixes, values)
  assert.equal(data.rules.docstring_region.region_name, 'on')
  assert.ok(!validateConfig(data).some(issue => issue.level === 'error'))
})
