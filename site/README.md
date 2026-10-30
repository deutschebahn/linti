# LinTi documentation site

The Docus site lives inside the LinTi repository. Its rule reference is exported
from the Python rule registry; Pyodide runs the actual wheel in a Web Worker.
The `/playground` page lints whole pasted processes through
`linti.linter.text_api.lint_text` (format auto-detection, `linti.yaml`, auto-fix).

The `/config` page builds a `linti.yaml`. Its form is generated from
`app/data/config-schema.json`: the pydantic `Config` schema (field help comes
from `Field(description=...)`), the defaults, and the use-case presets from
`linti.config_presets`. The YAML text is the only state. Form edits go through
`app/utils/lintiConfig.ts`, which edits the YAML document in place and keeps
only settings that differ from the defaults. The configurator, the playground
and the rule reference share local drafts and named configurations via
`useConfigLibrary()`, which uses `localStorage` and `#config=` share links.
Every change is written back at once; another tab's write arrives through the
`storage` event and replaces the profiles here while each tab keeps its own
draft (last write wins). A share link pasted into an already open page is
imported as well.

Shared building blocks: `<CodeEditor>` (CodeMirror behind `v-model`),
`<FindingsList>` (summary and clickable findings of a lint run) and
`useLintiWorker()`, which runs typed requests in the Pyodide worker and
resolves with the result, or with null when the run failed or was replaced.

The three tools lay themselves out by the width Docus gives them (CSS
container queries on `.lint-tool`), not by the viewport, and take the full
page width (`app/app.css`). Confirmations and choices (`ask`, `choose`) go
through `useConfirm()` and `<ConfirmDialog>` (a `UModal`) rather than
`window.confirm()`. `e2e/layout.spec.mjs` checks
phone, tablet and desktop widths.

`scripts/generate_all_rules.py` regenerates both `app/data/*.json` files; never
edit them by hand.

```bash
python -m pip install -e .
python scripts/generate_all_rules.py
python -m pip wheel --no-deps --wheel-dir site/public/wheels .
cd site
npm ci
node scripts/prepare-assets.mjs
node scripts/write-wheel-manifest.mjs
npm run dev
```

Run `npm run generate` to build the static site in `.output/public`. All Pyodide
assets are self-hosted. The Pages workflow runs the above preparation steps,
`npm run test:unit`, `npm run typecheck` and the Playwright tests on pull
requests and `main`, but deploys only from `main`, under `/linti/`. Canonical
URLs, `og:url` and the sitemap use `https://deutschebahn.github.io/linti`
(`nuxt.config.ts`). Docus' MCP server is disabled, since a static Pages build
cannot serve it.

The rule reference intentionally keeps `ALL_RULES.md` for existing GitHub links.
Once this site is established, the old Markdown generator can be retired
separately.
