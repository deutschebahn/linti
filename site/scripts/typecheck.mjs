/** Typecheck the site while isolating known errors in the pinned Docus package.
 * Remove this allowlist when the upstream errors are fixed. New diagnostics,
 * including in Docus, still fail CI.
 */
import { spawnSync } from 'node:child_process'

const knownVendorErrors = [
  'node_modules/docus/app/composables/useSeo.ts:TS2339',
  'node_modules/docus/app/composables/useSeo.ts:TS2339',
  'node_modules/docus/app/composables/useSeo.ts:TS2322',
  'node_modules/docus/app/composables/useSeo.ts:TS2322',
  'node_modules/docus/app/plugins/i18n.ts:TS2339',
  'node_modules/docus/modules/assistant/runtime/composables/useAssistant.ts:TS2339',
]
// useSeo has four known diagnostics, i18n and assistant one each.
const check = spawnSync(process.execPath, ['node_modules/@nuxt/cli/bin/nuxi.mjs', 'typecheck'], {
  encoding: 'utf8',
  maxBuffer: 10 * 1024 * 1024,
})
const output = `${check.stdout || ''}${check.stderr || ''}`
if (check.error) throw check.error
if (check.status === 0) {
  console.log('Nuxt typecheck passed.')
  process.exit(0)
}
const errors = [...output.matchAll(/^([^\n]+)\(\d+,\d+\): error (TS\d+):/gm)]
  .map(([, file, code]) => `${file}:${code}`)
if (errors.length === knownVendorErrors.length
  && errors.every((error, index) => error === knownVendorErrors[index])
  && !/error TS\d+:/.test(output.replace(/^.*\(\d+,\d+\): error TS\d+:.*$/gm, ''))) {
  console.log(`Nuxt typecheck: application code passed; ${errors.length} known Docus 5.13.0 diagnostics remain upstream.`)
} else {
  process.stderr.write(output)
  process.exit(check.status || 1)
}
