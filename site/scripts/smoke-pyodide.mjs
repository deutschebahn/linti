/** Exercise the same Python bridge against the generated, self-hosted assets. */
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { loadPyodide } from 'pyodide';
import { Module } from 'node:module';
import { build } from 'esbuild';

const root = new URL('../public/', import.meta.url);
const manifest = JSON.parse(await readFile(new URL('linti-wheel.json', root), 'utf8'));
const pyodide = await loadPyodide({ indexURL: new URL('pyodide/', root).pathname });
await pyodide.loadPackage(['micropip', 'pydantic', 'pyyaml']);
pyodide.globals.set('wheel_url', new URL(`wheels/${manifest.wheel}`, root).href);
await pyodide.runPythonAsync('import micropip\nawait micropip.install(wheel_url, deps=False)');
await pyodide.runPythonAsync(await readFile(new URL('linti-bridge.py', root), 'utf8'));
const run = pyodide.globals.get('run_linti');
const runPlayground = pyodide.globals.get('run_playground');
const validate = pyodide.globals.get('validate_config');

try {
  const finding = JSON.parse(run('nValue=1;', 'prolog', 'F220', false));
  assert.ok(finding.issues.some(issue => issue.rule_id === 'F220'));
  const fixed = JSON.parse(run('nValue=1;', 'prolog', 'F220', true));
  assert.ok(fixed.fixes > 0);
  assert.ok(fixed.code.includes('nValue = 1;'));
  // Example context (linti.yaml, parameters) must reach the rule.
  const lowercase = JSON.stringify({ config: 'rules:\n  keyword_casing:\n    style: lowercase\n' });
  assert.equal(JSON.parse(run('if (x = 1);\nendif;', 'prolog', 'F110', false, lowercase)).issues.length, 0);
  assert.ok(JSON.parse(run('IF (x = 1);\nENDIF;', 'prolog', 'F110', false, lowercase)).issues.length > 0);
  const parameter = JSON.stringify({ parameters: ['pFactor'] });
  assert.equal(JSON.parse(run("pFactor = 2;", 'prolog', 'C210', false, parameter)).issues.length > 0, true);
  assert.equal(JSON.parse(run('nValue = 1', 'prolog', 'P110', false, JSON.stringify({ config: 'severity: error\n' }))).issues.length, 0);
  assert.ok(JSON.parse(run('IF (x = 1);\nIF (y = 2);\nENDIF;\nENDIF;', 'prolog', 'F220', false, JSON.stringify({ config: 'max_nesting_depth: 1\n' }))).issues.some(issue => issue.rule_id === 'P900'));
  assert.equal(JSON.parse(validate('rules:\n  keyword_casing:\n    enabled: "false"\n')).valid, true);
  assert.equal(JSON.parse(validate('rules: [')).valid, false);

  // Cross-check the real configurator parser/serializer against Core's loader.
  const bundle = await build({
    entryPoints: [new URL('../app/utils/lintiConfig.ts', import.meta.url).pathname],
    bundle: true,
    format: 'cjs',
    platform: 'node',
    write: false,
  });
  const configModule = new Module('lintiConfig.cjs');
  configModule._compile(bundle.outputFiles[0].text, 'lintiConfig.cjs');
  const { parseConfig, setOption, stringifyConfig } = configModule.exports;
  const coreConfig = (text) => {
    pyodide.globals.set('config_yaml', text);
    return JSON.parse(pyodide.runPython('json.dumps(config_from_text(config_yaml).model_dump(mode="json", by_alias=True))'));
  };
  for (const directive of ['', '%YAML 1.2\n---\n']) {
    const text = `${directive}max_nesting_depth: 010\n`;
    assert.equal(parseConfig(text).data.max_nesting_depth, coreConfig(text).max_nesting_depth);
    assert.equal(coreConfig(text).max_nesting_depth, 8);
    const { doc } = parseConfig(text);
    setOption(doc, ['target_version'], 'v12', null);
    assert.equal(coreConfig(stringifyConfig(doc)).max_nesting_depth, 8);
  }
  for (const value of ['on', 'off', 'yes', 'no', 'true', 'false', 'y', 'n']) {
    const text = `rules:\n  keyword_casing:\n    enabled: ${value}\n`;
    const data = parseConfig(text).data;
    // The unquoted y/n stay strings in PyYAML, then pydantic coerces them.
    const expected = ['on', 'yes', 'true', 'y'].includes(value);
    assert.equal(coreConfig(text).rules.keyword_casing.enabled, expected);
    assert.equal(typeof data.rules.keyword_casing.enabled, ['y', 'n'].includes(value) ? 'string' : 'boolean');
  }
  const strings = ['on', 'off', 'yes', 'no', 'true', 'false', '010', '08', 'y', 'n', '2026-10-04'];
  const { doc } = parseConfig('');
  setOption(doc, ['generic_prefixes'], strings, []);
  setOption(doc, ['rules', 'docstring_region', 'region_name'], 'on', 'Docstring');
  const generated = stringifyConfig(doc);
  assert.equal(JSON.parse(validate(generated)).valid, true);
  assert.deepEqual(coreConfig(generated).generic_prefixes, strings);
  assert.equal(coreConfig(generated).rules.docstring_region.region_name, 'on');

  const paCode = await readFile(new URL('../../example/playground/process-pa.ti', import.meta.url), 'utf8');
  const process = JSON.parse(runPlayground(paCode, '', false));
  assert.equal(process.format, 'pa');
  assert.ok(process.issues.some(issue => issue.rule_id === 'F110' && issue.procedure === 'prolog' && issue.line === 4));
  assert.ok(process.issues.some(issue => issue.rule_id === 'C220'));
  const fixedProcess = JSON.parse(runPlayground(paCode, '', true));
  assert.ok(Object.values(fixedProcess.fixes).reduce((a, b) => a + b, 0) > 0);
  assert.ok(fixedProcess.code.includes('#JSON_PROPERTIES'));
  assert.match(JSON.parse(runPlayground(paCode, 'rules: [', false)).error, /Invalid linti\.yaml/);
  console.log('LinTi/Pyodide smoke test passed (rule with example context, whole-process lint and auto-fix).');
} finally {
  run.destroy();
  runPlayground.destroy();
  validate.destroy();
}
