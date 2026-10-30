import { readdir, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const wheelDirectory = fileURLToPath(new URL('../public/wheels/', import.meta.url));
const wheels = (await readdir(wheelDirectory)).filter(name => /^linti-.*-py3-none-any\.whl$/.test(name));
if (wheels.length !== 1) throw new Error(`Expected exactly one LinTi wheel, found: ${wheels.join(', ')}`);
await writeFile(path.join(path.dirname(wheelDirectory), 'linti-wheel.json'), JSON.stringify({ wheel: wheels[0] }) + '\n');
