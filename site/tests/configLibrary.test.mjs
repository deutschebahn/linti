import assert from 'node:assert/strict'
import test from 'node:test'
import { decodeSharedConfig, emptyLibrary, encodeSharedConfig, nameProblem, parseLibrary, removeProfile, saveProfile, uniqueName } from '../app/utils/configLibrary.ts'

test('a stored library round-trips through parseLibrary', () => {
  const library = saveProfile({ ...emptyLibrary(''), draft: { yaml: '# CI\n', baseId: null, name: 'CI' } }, 'CI', 'id-1', '2026-09-27')
  assert.deepEqual(parseLibrary(JSON.stringify(library)), library)
  assert.equal(parseLibrary(JSON.stringify(emptyLibrary('')))?.profiles.length, 0)
})

test('rejects corrupt storage without discarding a valid library', () => {
  assert.equal(parseLibrary('{'), null)
  assert.equal(parseLibrary('{"version":2,"profiles":[],"draft":{}}'), null)
  assert.equal(parseLibrary('{"version":1,"profiles":[{}],"draft":{"yaml":"","name":"","baseId":null}}'), null)
})

test('keeps multiple profiles independent and resets only a deleted active profile', () => {
  const firstDraft = emptyLibrary('defaults')
  firstDraft.draft = { yaml: 'rules:\n  keyword_casing: {}', name: 'CI', baseId: null }
  const first = saveProfile(firstDraft, 'CI', 'id-1', '2026-09-27')
  const secondDraft = { ...first, draft: { yaml: 'rules:\n  indentation: {}', name: 'Dev', baseId: null } }
  const second = saveProfile(secondDraft, 'Dev', 'id-2', '2026-09-28')
  assert.deepEqual(second.profiles.map(profile => profile.name), ['CI', 'Dev'])
  assert.equal(second.profiles[0].yaml, 'rules:\n  keyword_casing: {}')
  assert.equal(second.draft.baseId, 'id-2')
  assert.throws(() => saveProfile(second, 'CI', 'id-3', '2026-09-29', true), /already exists/)
  const deleted = removeProfile(second, 'id-2', 'defaults')
  assert.deepEqual(deleted.profiles.map(profile => profile.name), ['CI'])
  assert.equal(deleted.draft.yaml, 'defaults')
  assert.equal(deleted.draft.baseId, null)
})

test('a named empty draft saves once and subsequent saves update the same profile', () => {
  const library = emptyLibrary('recommended preset')
  library.draft = { yaml: '', name: 'Fresh', baseId: null }
  const created = saveProfile(library, library.draft.name, 'fresh-id', '2026-09-29')
  assert.equal(created.profiles[0].yaml, '')
  assert.equal(created.draft.baseId, 'fresh-id')

  created.draft.yaml = 'rules:\n  indentation:\n    size: 2\n'
  const updated = saveProfile(created, created.draft.name, 'unused-id', '2026-09-30')
  assert.equal(updated.profiles.length, 1)
  assert.equal(updated.profiles[0].id, 'fresh-id')
  assert.equal(updated.profiles[0].yaml, created.draft.yaml)
})

test('share links preserve Unicode YAML and a profile name', () => {
  const yaml = '# Grüße 🌍\nrules:\n  keyword_casing:\n    enabled: false\n'
  const shared = { name: 'Meine Regeln', yaml }
  assert.deepEqual(decodeSharedConfig(`#config=${encodeSharedConfig(shared)}`), shared)
  assert.equal(decodeSharedConfig(`#config=${Buffer.from(yaml).toString('base64url')}`), null, 'unversioned payloads are rejected')
  assert.equal(decodeSharedConfig('#config=v1.not-json'), null)
  assert.equal(decodeSharedConfig(`#config=${'a'.repeat(8001)}`), null)
})

test('names stay unique, ignoring case, and a profile may keep its own name', () => {
  assert.equal(uniqueName(['Alpha', 'alpha (2)'], 'ALPHA'), 'ALPHA (3)')
  assert.equal(uniqueName([], 'Beta'), 'Beta')
  const library = { ...emptyLibrary(''), profiles: [{ id: 'a', name: 'Alpha', yaml: '', createdAt: '', updatedAt: '' }] }
  assert.match(nameProblem(library, '  '), /name/)
  assert.match(nameProblem(library, 'alpha'), /already exists/)
  assert.equal(nameProblem(library, 'alpha', 'a'), null)
})
