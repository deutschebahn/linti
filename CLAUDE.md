# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Linti is a linter, formatter, and auto-fixer for TM1 TurboIntegrator (TI) code. It lexes/parses TI scripts, runs a set of rules, reports issues, and can auto-fix the safe ones. Multiple on-disk process formats are supported through a provider abstraction.

## Commands

```bash
pip install -e ".[dev]"     # install with pytest + pre-commit
pytest                      # run the whole suite (config in pyproject.toml, -v is default)
pytest tests/test_keyword_casing.py            # single file
pytest tests/test_keyword_casing.py::test_name # single test
ruff check src tests        # lint (ruff is the project linter)
linti example/git-format.ti           # run the CLI against a file
linti example/git-format.ti --auto-fix
```

Note: if an editable install resolves `linti` to a different checkout on this
machine, run against the local tree with `PYTHONPATH=src python -m linti.cli.main ...`
and `PYTHONPATH=src pytest`.

## Project conventions (from .github/copilot-instructions.md)

- After adding a rule or changing rule metadata, regenerate docs with
  `python scripts/generate_all_rules.py`. **Never edit `ALL_RULES.md` by hand** —
  it is generated from each rule's `METADATA`.
- Run the full test suite after changes.
- Update `README.md` when behavior changes, and suggest a `pyproject.toml`
  version bump after a feature or fix.

## Architecture

The pipeline is: **provider → ProcessIR → (per procedure) lexer → parser/AST → linter (rules) → reporter / fixer**.

### Lexing & parsing
- `lexer/` turns TI source into a `Token` stream. `TokenWindow` gives rules
  lookaround access to neighboring tokens by index.
- `parser/` builds an AST (`parser/ast.py`) — `Program`, `IfStatement`,
  `WhileStatement`, etc. The parser is resilient (see `test_resilient.py`); it
  should not crash on malformed input.

### Providers (`provider/`)
Each input format implements the `ProcessProvider` protocol (`list_processes`,
`get_process`, `save_process`) and normalizes to a single in-memory
`ProcessIR` (`model/process_ir.py`). `provider/factory.py` picks the provider by
path. Formats: Git-deploy (`.json` + linked `.ti`), PA-code (`#SECTION` +
`#JSON_PROPERTIES`), YAML TM1 process files, and `.ti` variants (region-based
and plain). A `ProcessIR` exposes the four TI execution blocks
(Prolog/Metadata/Data/Epilog) as procedures via `extract_procedures`, plus
parameters/variables used by context-aware rules.

### Rules (`rules/`) — the core extension point
Two rule base classes in `rules/Rule.py`:
- `BaseRule` — **token-based**. Declares `interested_in()` → list of `TokenType`s;
  `visit(token, window, context)` returns `LintIssue`s.
- `BaseStatementRule` — **AST-based**. `interested_in()` → AST node types;
  optional `prepare(ast)` for a full pre-scan (e.g. lookahead); `visit(statement, context)`.

Rules **self-register**: `rules/__init__.py` walks the package with `pkgutil`
and imports every module, so `__init_subclass__` appends any class with a
non-empty `CONFIG_KEY` to `_RULE_REGISTRY`. **There is no manual rule list** —
adding a new rule module under `rules/<category>/` is enough to register it.
`rule_factory.create_rules(cfg, select)` iterates the registry, applies config
(`enabled`, per-rule options via `from_config`) and `--select` filtering, and
returns `(token_rules, statement_rules)`.

Rule IDs encode category + subcategory: `D`=documentation, `F`=format,
`N`=naming, `S`=semantic; e.g. `F110` (keyword casing), `F310` (indentation),
`N110` (variable prefix), `S130` (empty block). `--select` matches by full ID or
prefix (`F`, `F1`, `F11`). Each rule carries `RuleMetadata` (name, description,
`auto_fix`, examples) used by `linti explain` and `ALL_RULES.md` generation.

### Linter (`linter/`)
`Linter` (`linter/linter.py`) indexes rules by token type / AST node type, then
runs a single token pass followed by a recursive AST walk (`_visit_node`, which
maintains a `block_stack` of `if`/`while` for context). `reset()` is called on
every rule before each pass — stateful rules must implement it.

- `linter/api.py` — high-level orchestration: `lint_process_model` runs the full
  per-procedure pipeline; `lint_process` / `lint_all` drive a provider and
  optionally auto-fix then re-lint.
- `linter/constant_propagation.py` — process-wide `ConstantPropagationIndex`,
  shared by all sections and independent of the per-rule reset cycle. It tracks
  literal assignments and folded literal expressions across Prolog → Metadata →
  Data → Epilog; anything dynamic/conditional is unknown. Rules query it via
  `context.constant_value(name, line)` (returns `None` when unknown). Builds
  lazily on first access, so rules that don't use it cost nothing.
- `linter/lint_issue.py` — `LintIssue` and `Fix`. A rule is auto-fixable iff its
  issues carry a `Fix(position, old_value, new_value)`.
- `linter/fixer.py` — applies `Fix`es by position (descending, so offsets stay
  valid), iterating up to `MAX_AUTO_FIX_PASSES` until stable.
- `linter/noqa.py` — inline suppression (`# noqa: F110`, region begin/end,
  procedure-level). Applied after rules run, before reporting.
- `linter/reporter.py` — pure formatting functions producing report lines and
  summaries; the CLI just echoes them. Issues are `(proc_name, LintIssue, source_line)`
  tuples; line numbers in messages are offset by the procedure's source line.

### CLI (`cli/`)
`cli/main.py` is the Typer entry point (`linti = linti.cli.main:main`).
`cli/file_linter.py` wires providers + config + reporter for single-file and
directory runs. `cli/config_loader.py` discovers `linti.yaml` by walking upward
to a project root. `cli/rule_explainer.py` powers `linti explain`.

## Adding a rule (typical flow)
1. Create `rules/<category>/<name>_rule.py` subclassing `BaseRule` or
   `BaseStatementRule`; set `CONFIG_KEY`, `RULE_ID`, `METADATA`, and implement
   `interested_in` + `visit`. Attach a `Fix` to issues if it is safely fixable.
2. Add a test under `tests/`.
3. Run `python scripts/generate_all_rules.py` to refresh `ALL_RULES.md`.
4. Update `README.md` if user-facing, and bump the version in `pyproject.toml`.
