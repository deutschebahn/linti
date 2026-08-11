# Linti

## Description

A linter for TM1 TurboIntegrator (TI) code that enforces consistent formatting and best practices. Originally started as an internal project at Deutsche Bahn AG, it is now opened to the community. Contributions are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md) for details.

## Name Origin

The name "Linti" is a wordplay on "lint" and "TI" (TurboIntegrator). The "-i" ending is commonly used in German nicknames and was chosen intentionally as a small tribute to the project's German roots.

## Motivation

TurboIntegrator processes are the backbone of any TM1 application, yet there has never been a dedicated linter for TI code. Teams rely on manual code reviews and informal conventions that inevitably drift 
over time. We built Linti to close that gap — giving TM1 developers the same kind of automated quality checks that are standard in every other programming ecosystem.

We decided to open-source Linti because the TM1 community is relatively small. A linter only becomes truly useful when it reflects the collective experience of many teams, not just one. By publishing it, we hope to invite contributions from other TM1 practitioners and give back to a community that has always been generous with knowledge.

## Compatibility Notice

This project is an independent compatibility tool for TurboIntegrator (TI) scripts used in TM1.

It is not affiliated with, endorsed by, sponsored by, or maintained by IBM. TM1, Planning Analytics, and related product names are referenced for compatibility and identification purposes only.

## Feature

* Lexer
* Linter
* Rules
* Parser (AST)
* Formatter
* Provider-based input format support

## Supported Input Formats

### Fully Supported (all rules)

- Git-deploy process format (`.json` + linked `.ti`)
  - Reads metadata from JSON and code from `Code@Code.link`.
- PA-code format (`.ti`)
  - Uses `#SECTION Prolog|Metadata|Data|Epilog` and a trailing
    `#JSON_PROPERTIES` block for metadata.
- YAML TM1 process files (`.yaml`, `.yml`)
  - `!TM1py.ProcessObject` and `config.definition` formats.

### TI File Variants (partial support)

- Region-based `.ti` files (`#region Prolog|Metadata|Data|Epilog`)
  - Section-aware rules work (Prolog/Metadata/Data/Epilog context).
  - Rules that require metadata declarations (for example parameters/variables)
    are limited because plain `.ti` region files do not carry metadata blocks.
- Plain `.ti` files (no region markers)
  - Entire file is treated as Prolog.
  - Only Prolog-valid and section-independent rules are meaningful.

## Linting Processes on a TM1 Server

Processes can be linted straight off a TM1 server, without exporting them first.
This needs the optional `tm1` extra:

```bash
pip install "linti[tm1]"
```

Linting a server is **read-only**: linti never writes a process back, and
`--auto-fix` is not supported for TM1 connections (see
[Auto-Fix Feature](#auto-fix-feature)).

### Connection Profiles

Servers are described in a per-user `connections.yaml`, kept separate from the
project's `linti.yaml` so internal host names and service accounts do not end up
in a checked-in file. Its location is `~/.config/linti/connections.yaml` on
Linux, `~/Library/Application Support/linti/connections.yaml` on macOS and
`%APPDATA%\linti\connections.yaml` on Windows; `LINTI_CONNECTIONS` or
`--connections` override it.

```yaml
# connections.yaml — connection data only, never passwords
default_profile: prod

profiles:
  prod:
    address: tm1.corp.local
    port: 8010
    ssl: true
    user: admin
    # namespace: MyCAMNamespace   # for CAM authentication
    # verify: /path/to/server.cer # true, false, or a certificate path
    # timeout: 30
  dev:
    base_url: https://pa.example.com/api/v1
    user: svc_lint
```

**Passwords are never stored in this file.** The profile model has no `password`
field, and a `password:` (or `api_key:`, `cam_passport:`, …) key is rejected with
an error pointing at `linti tm1 login` — so a secret pasted in here fails loudly
on the next run instead of quietly sitting on disk.

### Credentials

Passwords live in the operating system's credential store (Windows Credential
Manager, macOS Keychain, Linux SecretService/KWallet) via
[keyring](https://pypi.org/project/keyring/):

```bash
linti tm1 login prod     # prompts, verifies against the server, then stores
linti tm1 logout prod    # removes the stored password
linti tm1 profiles       # lists profiles and whether a password is stored
```

`login` connects before it stores: a saved credential that does not work is
worse than none at all.

For CI, where there is no keyring, use an environment variable instead:

```bash
export LINTI_TM1_PROD_PASSWORD="…"   # per profile
export LINTI_TM1_PASSWORD="…"        # or one for the whole run
linti tm1 lint -p prod
```

The resolution order is: per-profile environment variable → generic environment
variable → keyring → interactive prompt (only when there is a terminal). There
is deliberately **no `--password` flag**: a password in the command line is
visible in the process list and lands in shell history.

### Linting

```bash
linti tm1 lint -p prod                      # every process on the server
linti tm1 lint -p prod "Sales.*" "Load_*"   # only matching names
linti tm1 lint -p prod --select F110
linti tm1 lint -p prod --fail-on warning
linti tm1 lint -p prod --include-control    # also TM1's own }/{ processes
```

Patterns are globs matched case-insensitively against process names (TM1 object
names are case-insensitive), and must be quoted so the shell does not expand
them. TM1's own control processes are skipped unless `--include-control` is
given.

Rules are configured exactly as for files: `linti.yaml` is discovered from the
current directory, or named with `--config`. Findings are reported against a
`tm1://<profile>/<process>` label, and line numbers count from the process's
real first line — the same numbers the TM1 process editor and
`tm1.processes.compile()` show. TM1's generated-statements block is not linted.

A process that cannot be fetched (locked, no permission) is reported at the end
and forces a non-zero exit, but does not abort the rest of the run.

> **Note:** `tm1` is a sub-command, so a *directory* named `tm1` needs the
> explicit form `linti lint tm1`.

## Install via Pypi

The linter is available on PyPI and can be installed using `pip install linti`.
Add the optional `tm1` extra (`pip install "linti[tm1]"`) to lint processes
directly on a TM1 server.

For a quick setup guide, see [GETTING_STARTED.md](GETTING_STARTED.md).

## Configuration

The linter can be configured using a `linti.yaml` configuration file. The file is automatically discovered and loaded from the same directory as the TI file being analyzed.

### Automatic Configuration Discovery

Place a `linti.yaml` file in your project. The linter searches upward from the file being linted until it finds a `linti.yaml`, reaches a project root (`.git`, `pyproject.toml`, `setup.cfg`, `setup.py`), or hits the filesystem root.

```bash
my-project/
├── linti.yaml              # Applies to all TI files below
├── processes/
│   ├── process1.ti
│   └── process2.ti
└── special/
    ├── linti.yaml          # Overrides for this directory
    └── process3.ti
```

When you run `linti processes/process1.ti`, the linter walks up and finds `my-project/linti.yaml`. Files in `special/` use their own local config instead.

### Custom Configuration File

You can also specify a custom configuration file:

```bash
linti process.ti --config custom-config.yaml
```

### Configuration Options

A typical `linti.yaml` file looks like this:

```yaml
rules:
  # F110 - Keyword Casing
  # Enforces consistent casing for keywords (IF, ENDIF, ELSE, WHILE, END)
  # Supported styles: uppercase, lowercase, camelcase
  keyword_casing:
    enabled: true
    style: uppercase

  # F310 - Block Indentation
  # Enforces indentation for IF/WHILE blocks and for continuation lines
  # size: number of spaces per indentation level
  # continuation_style: how a line that continues an earlier statement is
  #   indented - hanging (one level per open parenthesis), aligned (under the
  #   opening parenthesis), or ignore (leave hand-formatted lines alone)
  indentation:
    enabled: true
    size: 4
    continuation_style: hanging

  # F330 - Maximum Line Length
  # Flags lines over `limit` characters and rewraps them at argument or
  # operator boundaries, in the hanging style F310 enforces.
  max_line_length:
    enabled: true
    limit: 120

  # N110 - Variable Prefix Naming
  # Enforces TM1 naming conventions
  # - Numeric variables must start with 'n'
  # - String variables must start with 's'
  variable_prefix:
    enabled: true
    # Allow constants to start with 'c' (e.g., cRate, cMessage)
    # When enabled, constants may only be assigned once.
    allow_constant_prefix: false

  # C410 - Use Hierarchy-Aware Functions
  # Prefer hierarchy-aware functions (e.g. HierarchyElementExists,
  # ElementParent) over standard ones (e.g. DimensionElementExists, ELPAR).
  use_hierarchy_aware_functions:
    enabled: true
    # Base mode:
    # 'consistent' - either style is allowed, but mixing both in one file is reported
    # 'enforce'    - only hierarchy-aware functions are allowed
    mode: consistent

  # C430 - Do Not Use Undocumented Functions
  # Reports TI functions that IBM does not document or support (e.g.
  # DimensionElementInsertByAlias, LockOn, Hex).
  do_not_use_undocumented_functions:
    enabled: true
    # Functions the project knowingly relies on (case-insensitive).
    # Listed here they are never reported; use `# noqa: C430` for one-off cases.
    # allowed_functions:
    #   - DimensionElementInsertByAlias

  # C510 - Function Version Compatibility
  # Reports TI functions that are not available on the targeted PA/TM1 version.
  # Disabled by default: the target depends on your deployment strategy.
  function_version_compatibility:
    enabled: true
    # Optional override of the top-level `target_version` (see below):
    # 'CompatibleWithV11AndV12' - only functions available in both are allowed
    # 'V11'                     - flags functions introduced in v12
    # 'V12'                     - flags functions unsupported in v12
    mode: CompatibleWithV11AndV12

  # X130 - No Hardcoded Secrets
  # Reports secret-looking variables fed from a hardcoded string literal
  # (sPassword = 'letmein') or read out of a cube
  # (sPassword = CellGetS(...)). Neither the value nor the cube
  # coordinates are ever printed.
  # The value is taken from constant evaluation, so a literal split across
  # a concatenation (sPassword = 'let' | 'mein') or routed through another
  # variable is caught too. Half-known values (sPassword = 'prefix_' | pDyn)
  # are not reported - the secret itself may be the dynamic part.
  hardcoded_secret:
    enabled: true
    # Which names count as secret-looking (matched case-insensitively as
    # substrings of the variable name):
    # 'relaxed'  - password, passwd, pwd, secret
    # 'standard' - and apikey, api_key, token, credential
    # 'strict'   - and key, auth, cert, salt, signature
    # 'custom'   - only the names listed under `secret_names`
    mode: standard
    # Extra name fragments, added on top of the preset above
    # (and the whole list when mode is 'custom'):
    # secret_names:
    #   - kennwort
    # Accept credentials kept in a cube (CellGetS, AttrS, ...). Off by
    # default: the TM1 data directory can be encrypted, but rarely is,
    # so anyone with file access reads the value.
    allow_secrets_in_cubes: false
```

### Generic Processes

Some rules treat *generic* (templated) processes more strictly. A process is
considered generic when its name starts with one of the prefixes in the
top-level `generic_prefixes` setting. This single definition is shared by all
rules that care about it (currently `D110` Docstring Region and `C410`
Use Hierarchy-Aware Functions — generic processes are always held to C410's
`enforce` mode regardless of its base `mode`).

```yaml
# Top-level (shared across rules)
generic_prefixes:
  - '}core.'

rules:
  docstring_region:
    enabled: true
```

> **Deprecation:** `generic_prefixes` used to be configured under the docstring
> rule (`rules.docstring_region.generic_prefixes`). That still works on its own,
> but emits a warning — move it to the top-level `generic_prefixes` setting
> instead. Setting **both** the top-level and the per-rule value is a config
> error: linting fails immediately with a message telling you to remove the
> deprecated `rules.docstring_region.generic_prefixes` key.

`rules.one_space_before_equals` has been removed along with the Equals Spacing
rule. If it is still present in an older config, linti warns and ignores it.
Its old ID `F210` is not claimed by any live rule.

### Target Version

Which Planning Analytics / TM1 version your code has to run on is a project-wide
fact, so it lives in the top-level `target_version` setting. Version-aware rules
(currently `C510` Function Version Compatibility) read it from there:

```yaml
# Top-level (shared across rules)
target_version: both   # v11 | v12 | both

rules:
  function_version_compatibility:
    enabled: true
```

`target_version` only *supplies* the version — it never enables a rule. `C510` is
opt-in and stays silent until you set `enabled: true`.

A rule may override the shared value, either with its own `mode` or with a
per-rule `target_version`. Both are accepted; `mode` wins if you set both:

```yaml
target_version: v12

rules:
  function_version_compatibility:
    enabled: true
    mode: V11            # this rule checks against v11 regardless
```

Each key has its own spelling, and each accepts **only** its own:

| Key | Accepted values |
|-----|-----------------|
| `target_version` (top-level or per-rule) | `v11`, `v12`, `both` |
| `mode` (per-rule) | `V11`, `V12`, `CompatibleWithV11AndV12` |

`both` and `CompatibleWithV11AndV12` select the same behaviour, but each spelling
belongs to one key only — `mode: both` and `target_version: V11` are rejected
with a config error. With neither key set, `C510` defaults to
`CompatibleWithV11AndV12`.

### Excluding Files from Linting

The top-level `exclude_paths` key lists files, directories, or glob patterns to
skip during discovery:

```yaml
exclude_paths:
  - generated/
  - vendor/
  - "**/archive/*.ti"
```

- Entries may be individual files (`processes/test.ti`), directories
  (`generated/`), or glob patterns (`**/archive/*.ti`) — all use one common
  matcher.
- A bare name (no `/`, e.g. `generated`) excludes that file or directory
  *anywhere* in the tree (gitignore-style). A pattern containing a `/` (e.g.
  `processes/test.ti`) is anchored to the discovery root — prefix it with
  `**/` to match at any depth.
- CLI `--exclude-path` values **extend** this list rather than replacing it, so
  the effective exclusions are the configured ones plus the CLI ones (duplicates
  removed).

### Input Limits

To stay robust on large or untrusted process files, linti bounds two things via
top-level settings (safe defaults; normal files are unaffected):

```yaml
# Reject files larger than this many bytes before reading them into memory.
max_file_size: 10485760   # 10 MB (default)

# Cap on control-flow (IF/WHILE) nesting depth. Deeper nesting is reported as
# a P900 diagnostic instead of being parsed unboundedly.
max_nesting_depth: 150    # default

# Cap on how many distinct values the constant evaluation index tracks per
# variable (across IF/ELSE branches) before treating it as unknown. Used by
# value-aware rules such as X210 and C410.
max_values_per_variable: 8           # default
```

- A file above `max_file_size` fails with a clear error rather than being read.
- A procedure nested beyond `max_nesting_depth` produces a single `P900`
  diagnostic (`Maximum nesting depth (N) exceeded`) for that procedure and
  linting continues. `P900` is raised by the parser rather than by a rule
  module, so it has no entry in `linti explain` / `ALL_RULES.md` — but it takes
  the same `enabled` and `severity` settings as a real rule:

  ```yaml
  rules:
    nesting_depth:
      severity: error    # default: warning (does not fail the run)
      enabled: false     # drop the diagnostic entirely
  ```

  With `enabled: false` an unparseable-because-too-deep procedure is skipped
  silently — no rule ever sees it, and nothing says so.
- `max_values_per_variable` bounds cross-section constant evaluation: once a variable
  could hold more than this many distinct literal values, it degrades to
  "unknown" so value-aware rules stay conservative rather than tracking an
  unbounded set.

### All rules

For a complete reference of all linting rules with detailed configuration examples and usage instructions, see [ALL_RULES.md](ALL_RULES.md).

### Disabling Rules

To disable a specific rule, set `enabled: false`:

```yaml
rules:
  keyword_casing:
    enabled: false
  variable_prefix:
    enabled: true
```

### Inline Suppression (`noqa`)

You can suppress specific rules directly in TI code using `# noqa` comments.
TI uses `#` for comments, so the syntax feels natural.

#### Trailing comment — suppress current line

```
nVar=1;  # noqa: F220
```

#### Standalone comment — suppress the next code line

```
# noqa: F110
if(nVar = 1);
```

#### Procedure-level — first comment before any code suppresses the entire file/procedure

```
# noqa: X110, C310
ExecuteCommand(sCmd, 1);
RunProcess(pProcess);
```

#### Region — suppress a block of lines

```
# noqa-begin: F110
if(nVar = 1);
endif;
# noqa-end: F110
```

Multiple rule IDs can be combined with commas: `# noqa: F110, N110, C220`

Deprecated rule IDs (see [Rule ID migration](#rule-id-migration)) still work in
`noqa` comments for one deprecation cycle; linti resolves them to the canonical
ID and prints a warning telling you which ID to use instead.

## CLI Usage

### Basic Usage

```bash
# Lint a single file
linti process.ti

# Lint with additional debug output
linti process.ti --tokens
linti process.ti --ast
linti process.ti --tokens --ast

# Lint with custom configuration
linti process.ti --config my-config.yaml

# Auto-fix issues
linti process.ti --auto-fix

# Lint a region-based TI file
linti process-regions.ti --auto-fix

# Lint a YAML ProcessObject file
linti process.yaml --auto-fix

# Lint a Git-deploy process (JSON + linked .ti)
linti process.json --auto-fix

# Lint a PA-code process (#SECTION + #JSON_PROPERTIES)
linti pa-code.ti --auto-fix

# Lint all process files in a directory (searched recursively)
linti processes/ --auto-fix
```

### Input Paths and Globs

The positional `<path>` argument accepts individual files, directories, and glob
patterns — and you can pass several at once. linti performs the glob expansion
itself, so patterns behave the same across shells and platforms (quote them so
your shell does not expand them first).

```bash
# A single file, a directory, or a glob
linti process.ti
linti processes/
linti "*.ti"
linti "processes/**/*.ti"     # ** recurses into sub-directories
linti processes/*.json

# Several paths (files, directories, and globs) expanded together
linti processes/ "*.yaml" other/process.ti
```

A file reached through more than one input (overlapping paths or globs) is
**linted only once**.

### Excluding Paths

Skip files, directories, or glob patterns with the repeatable `--exclude-path`
option:

```bash
linti . \
    --exclude-path generated \
    --exclude-path vendor \
    --exclude-path "**/archive/*.ti"
```

Exclusions can also be configured in `linti.yaml` via the top-level
[`exclude_paths`](#excluding-files-from-linting) key. CLI `--exclude-path`
values **extend** the configured list (they never replace it), and duplicates
are ignored.

### Command Help

```bash
linti --help       # Overview of all commands and global options
linti lint --help  # All linting arguments and options (--auto-fix, --select, ...)
```

`lint` is the default command — `linti process.ti` is a shortcut for `linti lint process.ti`.

### Report Output

Every report closes with a summary that reads bottom-up: the per-rule breakdown
first, the run's totals last — so in a terminal the verdict is what stays on
screen. The breakdown is sorted ascending by count, putting the rule worth
tackling first directly above the totals, and names how many of each rule's
findings `--auto-fix` can clear.

```
======================================================================
Issues by rule:
  D110  1               Docstring Region
  C110  1               Empty Block
  F250  2  (2 fixable)  One Space Inside Parentheses
  F270  2  (2 fixable)  No Trailing Whitespace

Total Issues: 6 (Auto-fixable: 4)
Run: linti example/git-format.ti --auto-fix
```

Directory runs get the same block, counted across all files, inside the
`SUMMARY` section above `Total Files` / `Total Issues`. Counts always reflect
what was printed: findings dropped by [`--severity`](#severity) are filtered out
before anything is counted.

### Selecting Specific Rules

Use the `--select` option to run only specific rules or groups of rules:

```bash
# Run a specific rule
linti process.ti --select F110

# Run all rules in a category (e.g., all Format rules)
linti process.ti --select F

# Run all rules in a subcategory (e.g., all F2xx - Whitespace rules)
linti process.ti --select F2

# Run multiple rules or groups (comma-separated)
linti process.ti --select F110,C220
linti process.ti --select F,N1,C3

# Combining with other options
linti process.ti --select F --auto-fix
linti process.ti --select N,C --tokens
```

Two more options adjust the set instead of replacing it. Both take the same
patterns as `--select`, and both are repeatable as well as comma-separated:

```bash
# Run the configured set plus one opt-in rule
linti process.ti --extend-select D110

# Skip a rule for this run (--ignore is an alias of --exclude-rule)
linti process.ti --ignore F220
linti process.ti --exclude-rule F2,D110

# Repeatable, and combinable with --select
linti process.ti --ignore F220 --ignore C110
linti process.ti --select F --extend-select D110 --ignore F250
```

**Precedence**, highest first:

1. `--exclude-rule` / `--ignore` — a matching rule never runs, not even when
   another option asked for it.
2. `--select` — replaces the configured set entirely.
3. `--extend-select` / `--extend-select` — adds to whatever is in effect, on
   top of `--select` or, without it, on top of the configured set.
4. Otherwise the per-rule `enabled` setting from `linti.yaml` decides.

`--select` and `--extend-select` both run the rules they match even when the
config sets `enabled: false` for them.

**Selection patterns:**
- `F`, `N`, `D`, `C`, `X`, `P` – Select all rules in a category
- `F1`, `F2`, `F3`, `N1`, `N2`, `D1`, `C1`, `C2`, `C3`, `C4`, `X1`, `X2`, `P1` – Select all rules in a subcategory
- `F110`, `D110`, `C220` – Select a specific rule

A deprecated rule ID is accepted as a full ID (e.g. `--select S220` runs `C220`)
and warns; group prefixes are matched against canonical IDs only.

`P900` is the one exception: it's enforced directly in the parser rather than
by a rule module, so `--select` (and `# noqa`) cannot target it either way —
only `rules.nesting_depth.enabled`/`severity` in `linti.yaml` control it.
Naming `P900` in any of the three options is therefore inert, and linti says so
instead of doing nothing quietly:

```
⚠  --exclude-rule P900 has no effect: it is enforced directly in the parser
   rather than by a rule module, so there is no rule to select or skip. Raise
   `max_nesting_depth` (top-level config key, default 150) if your code
   genuinely nests that deep, or set `rules.nesting_depth.enabled: false` to
   silence the diagnostic.
```

A group prefix such as `--ignore P` is a normal exclusion — it simply never
reaches `P900`.

A pattern that matches no rule at all gets the same treatment, because a
mistyped ID is otherwise invisible: `--select F22O` would quietly lint nothing
and `--ignore F22O` would quietly keep reporting.

```
⚠  --exclude-rule F22O matches no rule and has no effect. Run `linti explain`
   to list the available rule IDs.
```

The pattern is left in place either way — a typo in `--select` still means
"run only these rules", never "run everything". Warnings are emitted once per
run, not once per linted file.

### Listing Rules

Use the `explain` subcommand to inspect available rules and view detailed guidance for one rule.

```bash
# List all rules with short description and auto-fix support
linti explain

# Explain a specific rule in detail
linti explain F110
```


## Rule Groups

Rules are organized by topic, each with a hierarchical numbering scheme. The
first letter is the category; the hundreds digit is a logical subcategory.

| Letter | Category |
|--------|----------|
| `F` | Formatting |
| `N` | Naming |
| `D` | Documentation |
| `C` | Code Quality |
| `X` | External Interactions |
| `E` | Error |

### Formatting Rules (F1xx, F2xx, F3xx)
Formatting and code style rules:

- **F1xx - Casing**: Keyword capitalization
  - `F110` - Keyword Casing

- **F2xx - Whitespace**: Whitespace and spacing requirements
  - `F220` - Whitespace Around Operators
  - `F230` - Whitespace After Comma
  - `F240` - No Space Before Semicolon
  - `F250` - One Space Inside Parentheses
  - `F260` - No Multiple Spaces
  - `F270` - No Trailing Whitespace

- **F3xx - Layout**: Indentation, line breaks, and code layout
  - `F310` - Block Indentation
  - `F320` - One Statement Per Line
  - `F330` - Maximum Line Length

### Naming Rules (N1xx, N2xx)
Variable and parameter naming conventions:

- **N1xx - Variables**: Variable prefix and casing conventions
  - `N110` - Variable Prefix Naming
  - `N120` - Variables Consistent Casing

- **N2xx - Inputs**: Naming conventions for parameters and data sources
  - `N210` - Parameter Naming
  - `N220` - Data Source Variable Naming

### Documentation Rules (D1xx)
Documentation and process docstring validation:

- **D1xx - Documentation**: Required docstring regions and headers
  - `D110` - Docstring Region

### Code Quality Rules (C1xx, C2xx, C3xx, C4xx, C5xx)
Control flow, mutability, and TM1 best practices:

- **C1xx - Control Flow**: Process execution and control flow patterns
  - `C110` - Empty Block
  - `C120` - Conditional Control Flow
  - `C130` - ItemSkip Block Usage
  - `C140` - Unreachable Code

- **C2xx - Variables**: Variable mutability and assignment constraints
  - `C210` - Read-only Parameters and Variables
  - `C220` - Single-assignment Constants

- **C3xx - Process Design**: How processes call one another
  - `C310` - Literal Process Calls

- **C4xx - TM1 Best Practices**: Idiomatic TM1 API usage
  - `C410` - Use Hierarchy-Aware Functions
  - `C430` - Do Not Use Undocumented Functions

- **C5xx - Version Compatibility**: Compatibility with a target PA/TM1 version
  - `C510` - Function Version Compatibility

### External Interactions Rules (X1xx, X2xx)
Interactions with systems outside the TI process:

- **X1xx - Security**: Security-sensitive operations
  - `X110` - No ExecuteCommand
  - `X120` - ODBCOpen Password Parameter
  - `X130` - No Hardcoded Secrets

- **X2xx - Performance**: Cost of external data access
  - `X210` - Filter ODBC Rows in SQL

### Parser Rules (P1xx, P9xx)
Diagnostics enforced by the parser itself rather than a lint pass over a
finished AST:

- **P1xx - Parsing**: Statements the parser could not understand
  - `P110` - Unparseable Statement
- **P9xx - Safety Limits**: Input-hardening caps that abort parsing instead of
  crashing
  - `P900` - Maximum Nesting Depth Exceeded — control-flow nesting beyond
    `max_nesting_depth` (default 150) aborts that procedure's parse instead of
    recursing into a `RecursionError`. Configured under `rules.nesting_depth`
    (`enabled`/`severity`), but **the cap itself is not optional** —
    `enabled: false` only silences the diagnostic; the procedure is still
    dropped from linting either way. See `linti explain P900` for the full
    story.

Use `linti explain` to list all rules or `linti explain <RULE_ID>` for detailed information about a specific rule.

### Severity

Every rule carries a severity. `error` is the default and fails the run;
`warning` is reported but exits 0.

The parse diagnostics `P110` and `P900` are warnings, because linti cannot tell
their two possible causes apart from the inside: either the TI really is
malformed — yours to fix — or linti's parser does not cover a construct TM1
accepts, which is a linti bug. A build should not break on the second case, so
by default it does not. The report still names the count prominently, because a
finding nobody sees is a finding nobody reports back.

Override the weight of any rule in `linti.yaml`:

```yaml
rules:
  unknown_statement:
    severity: error      # promote P110 back to blocking
  keyword_casing:
    severity: warning    # report casing, but never fail on it
```

Two flags control the run as a whole:

```bash
linti processes/ --fail-on warning    # fail on warnings too (default: error)
linti processes/ --severity error     # only report errors; warnings are dropped
```

`--severity` filters before anything is counted, so a finding you asked not to
see can never fail your build — even together with `--fail-on warning`. Both
settings exist in `linti.yaml` under the same names:

```yaml
fail_on: error      # error (default) | warning
severity: warning   # warning (default) | error
```

A CI pipeline that wants the information without the breakage needs no flags at
all; one that treats every finding as blocking adds `--fail-on warning`.

### Rule ID migration

The former generic **Semantic (S)** category was split into **Code Quality (C)**
and **External Interactions (X)**, and a few rules were renumbered so each
subcategory describes its topic. The **Error (E)** category was also renamed to
**Parser (P)**, since its rules report parsing diagnostics (default severity
`warning`), not `error`-severity findings — and the parser-enforced
nesting-depth diagnostic (formerly `S900`, no rule class of its own) joined
that same group as `P900`. **Old IDs keep working for one deprecation cycle**
wherever a rule is referenced by ID — `--select`, `# noqa` comments, and
`linti explain`. Using one resolves to the canonical rule and prints:

```
⚠  Rule ID S220 is deprecated. Use C220 instead.
```

Diagnostics always report the **canonical (new)** ID.

| Old | New | Rule |
|-----|-----|------|
| `N230` | `N120` | Variables Consistent Casing |
| `D410` | `D110` | Docstring Region |
| `S130` | `C110` | Empty Block |
| `S110` | `C120` | Conditional Control Flow |
| `S120` | `C130` | ItemSkip Block Usage |
| `S210` | `C210` | Read-only Parameters and Variables |
| `S220` | `C220` | Single-assignment Constants |
| `S310` | `C310` | Literal Process Calls |
| `S410` | `C410` | Use Hierarchy-Aware Functions |
| `S320` | `X110` | No ExecuteCommand |
| `S330` | `X120` | ODBCOpen Password Parameter |
| `S340` | `X210` | Filter ODBC Rows in SQL |
| `E110` | `P110` | Unparseable Statement |
| `S900` | `P900` | Maximum Nesting Depth Exceeded |

Every other rule (all Formatting and Naming IDs) keeps the ID it already had.

> Configuration in `linti.yaml` is keyed by rule *name* (e.g. `keyword_casing`,
> `constant_assignment`), not by rule ID, so no config changes are needed.

### Auto-Fix Feature

The linter offers an automatic fix for many rules whenever the fix is safe to apply. In the linting issue report, every issue that can be fixed automatically is marked with a 🔧 indicator, so you can see at a glance which rules will be resolved. Apply the fixes with the `--auto-fix` flag.

Auto-fix applies to files only. Processes read from a TM1 server
(`linti tm1 lint`) are still marked with 🔧 where a fix exists, but linti does
not write them back — see [Linting Processes on a TM1 Server](#linting-processes-on-a-tm1-server).

### Multi-line Statements

A statement that does not fit on one line is laid out in a **hanging indent**: the opening parenthesis stays at the end of its line, everything inside it is indented one level deeper, and the line that closes it returns to the level of the line that opened it.

```ti
IF( nA = 1 );
    sValue = CellGetS(
        'Cube',
        'Element'
    );
ENDIF;
```

Long conditions and concatenations break before their operators:

```ti
IF(
    nA = 1
    & nB = 2
);
```

`F310` enforces this layout and `F330` produces it when a line exceeds the limit, so the two never disagree.

Two things auto-fix will not do: it never joins short lines back together, and it never rewraps a statement that contains a comment or a multi-line string literal — moving either could change what the code means. Such lines are reported without a 🔧.

If your project already wraps arguments by hand and you would rather keep that layout, set `continuation_style` to `aligned` (line wrapped content up under the opening parenthesis) or `ignore` (leave continuation lines alone entirely):

```yaml
rules:
  indentation:
    continuation_style: ignore
```

## TM1 Block Context Awareness

The linter understands TM1's four execution blocks when procedure sections are available (YAML, Git JSON+TI, PA-code `.ti`, or region-based `.ti`):

- **Prolog**: Initialization and setup code
- **Metadata**: Dimension/hierarchy manipulation code
- **Data**: Record-by-record data processing
- **Epilog**: Finalization and cleanup code

Rules can use block context to enforce block-specific requirements. For example:
- The ItemSkip rule (`C130`) only allows `ItemSkip()` in the Metadata or Data blocks
- Rules could require certain variable naming patterns based on the block

Metadata-dependent rules (for example checks based on declared Parameters/Variables)
require formats that provide metadata (`.yaml`, Git JSON+TI, PA-code).

For plain `.ti` files without `#region` sections, the full file is treated as **Prolog**.

## License

This project is licensed under the **Apache License 2.0**. See the [LICENSE](LICENSE) file for details.

The full license text is also available at the [Apache Software Foundation](https://www.apache.org/licenses/LICENSE-2.0).
