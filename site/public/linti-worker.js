/* Runs the real LinTi package in a browser worker, away from the UI thread. */
let runtime;
const MAX_CODE_BYTES = 10 * 1024 * 1024;
const MAX_CONFIG_BYTES = 256 * 1024;
const encoder = new TextEncoder();

function initialize() {
  runtime ||= load().catch((error) => {
    // Do not cache a failed start (e.g. a network hiccup): the next run retries.
    runtime = undefined;
    throw error;
  });
  return runtime;
}

async function load() {
  const assetRoot = new URL('./', self.location.href);
  const pyodideRoot = new URL('pyodide/', assetRoot).href;
  importScripts(new URL('pyodide/pyodide.js', assetRoot).href);
  const pyodide = await loadPyodide({ indexURL: pyodideRoot });
  await pyodide.loadPackage(['micropip', 'pydantic', 'pyyaml']);

  const manifest = await fetch(new URL('linti-wheel.json', assetRoot)).then((response) => {
    if (!response.ok) throw new Error('LinTi wheel manifest not found');
    return response.json();
  });
  const wheelURL = new URL(`wheels/${manifest.wheel}`, assetRoot).href;
  // deps=False: every asset is self-hosted, so micropip must not reach PyPI.
  // The in-memory linter needs only the packages loaded above; the CLI-only
  // dependencies (typer, rich, pathspec) are never imported.
  pyodide.globals.set('wheel_url', wheelURL);
  await pyodide.runPythonAsync('import micropip\nawait micropip.install(wheel_url, deps=False)');
  const bridge = await fetch(new URL('linti-bridge.py', assetRoot)).then((response) => {
    if (!response.ok) throw new Error('LinTi browser bridge not found');
    return response.text();
  });
  await pyodide.runPythonAsync(bridge);
  return pyodide;
}

// Each action names its Python entry point and how the request maps onto it.
// User input is passed as data, never interpolated into Python source.
const actions = {
  process: ['run_playground', data => [data.code, data.config || '', data.fix]],
  validate: ['validate_config', data => [data.config || '']],
  rule: ['run_linti', data => [data.code, data.procedure, data.ruleId, data.fix, JSON.stringify(data.context || {})]],
};

self.onmessage = async ({ data }) => {
  const { id, action = 'rule' } = data;
  try {
    if (!Object.hasOwn(actions, action)) throw new Error('Unknown lint action');
    if (encoder.encode(data.code || '').byteLength > MAX_CODE_BYTES) {
      throw new Error('Code is too large for the browser playground (10 MB limit).');
    }
    const configText = action === 'rule' ? data.context?.config : data.config;
    if (encoder.encode(configText || '').byteLength > MAX_CONFIG_BYTES) {
      throw new Error('Configuration is too large for the browser playground (256 KB limit).');
    }
    const pyodide = await initialize();
    // Loading is done; tell the page so its run timeout covers only the
    // (synchronous) lint itself, not the Pyodide download.
    self.postMessage({ id, status: 'running' });
    const [entryPoint, args] = actions[action];
    const run = pyodide.globals.get(entryPoint);
    try {
      const parsed = JSON.parse(run(...args(data)));
      self.postMessage(parsed.error ? { id, error: parsed.error } : { id, result: parsed });
    } finally {
      run.destroy();
    }
  } catch (error) {
    self.postMessage({ id, error: String(error?.message || error) });
  }
};
