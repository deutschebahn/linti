/** Self-host the pinned Pyodide runtime and only the wheels LinTi needs. */
import { copyFile, mkdir, readFile, writeFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const siteRoot = fileURLToPath(new URL('../', import.meta.url));
const packageRoot = path.join(siteRoot, 'node_modules/pyodide');
const output = path.join(siteRoot, 'public/pyodide');
const lock = JSON.parse(await readFile(path.join(packageRoot, 'pyodide-lock.json'), 'utf8'));
const { version } = JSON.parse(await readFile(path.join(packageRoot, 'package.json'), 'utf8'));
const packages = [
  'micropip', 'pydantic', 'pydantic-core', 'pyyaml',
  'annotated-types', 'typing-extensions', 'typing-inspection',
];

await mkdir(output, { recursive: true });
for (const name of ['pyodide.js', 'pyodide.asm.js', 'pyodide.asm.wasm', 'python_stdlib.zip', 'pyodide-lock.json']) {
  await copyFile(path.join(packageRoot, name), path.join(output, name));
}

const base = `https://cdn.jsdelivr.net/pyodide/v${version}/full/`;
for (const name of packages) {
  const entry = lock.packages[name];
  if (!entry) throw new Error(`Pyodide ${version} does not include ${name}`);
  const destination = path.join(output, entry.file_name);
  const response = await fetch(new URL(entry.file_name, base));
  if (!response.ok) throw new Error(`Could not fetch ${entry.file_name}: HTTP ${response.status}`);
  const bytes = Buffer.from(await response.arrayBuffer());
  const digest = createHash('sha256').update(bytes).digest('hex');
  if (digest !== entry.sha256) throw new Error(`Checksum mismatch for ${entry.file_name}`);
  await writeFile(destination, bytes);
  console.log(`Prepared ${entry.file_name}`);
}
