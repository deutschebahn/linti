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

## Install via Pypi

The linter is available on PyPI and can be installed using `pip install linti`.

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
  # Enforces indentation for IF/WHILE blocks
  # size: number of spaces per indentation level
  indentation:
    enabled: true
    size: 4

  # N110 - Variable Prefix Naming
  # Enforces TM1 naming conventions
  # - Numeric variables must start with 'n'
  # - String variables must start with 's'
  variable_prefix:
    enabled: true
    # Allow constants to start with 'c' (e.g., cRate, cMessage)
    # When enabled, constants may only be assigned once.
    allow_constant_prefix: false

  # S410 - Use Hierarchy-Aware Functions
  # Prefer hierarchy-aware functions (e.g. HierarchyElementExists,
  # ElementParent) over standard ones (e.g. DimensionElementExists, ELPAR).
  use_hierarchy_aware_functions:
    enabled: true
    # Base mode:
    # 'consistent' - either style is allowed, but mixing both in one file is reported
    # 'enforce'    - only hierarchy-aware functions are allowed
    mode: consistent
```

### Generic Processes

Some rules treat *generic* (templated) processes more strictly. A process is
considered generic when its name starts with one of the prefixes in the
top-level `generic_prefixes` setting. This single definition is shared by all
rules that care about it (currently `D410` Docstring Region and `S410`
Use Hierarchy-Aware Functions — generic processes are always held to S410's
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

`rules.one_space_before_equals` has been removed with rule `F210`. If it is still present in an older config, linti warns and ignores it.

### Input Limits

To stay robust on large or untrusted process files, linti bounds two things via
top-level settings (safe defaults; normal files are unaffected):

```yaml
# Reject files larger than this many bytes before reading them into memory.
max_file_size: 10485760   # 10 MB (default)

# Cap on control-flow (IF/WHILE) nesting depth. Deeper nesting is reported as
# an S900 diagnostic instead of being parsed unboundedly.
max_nesting_depth: 150    # default
```

- A file above `max_file_size` fails with a clear error rather than being read.
- A procedure nested beyond `max_nesting_depth` produces a single `S900`
  diagnostic (`Maximum nesting depth (N) exceeded`) for that procedure and
  linting continues. `S900` is a built-in parser diagnostic, not a configurable
  rule, so it does not appear in `linti explain` / `ALL_RULES.md`.

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
# noqa: S320, S310
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

Multiple rule IDs can be combined with commas: `# noqa: F110, N110, S220`

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

# Lint all YAML files in a directory
linti processes/ --auto-fix
```

### Command Help

```bash
linti --help
```

### Selecting Specific Rules

Use the `--select` option to run only specific rules or groups of rules:

```bash
# Run a specific rule
linti process.ti --select F110

# Run all rules in a category (e.g., all Format rules)
linti process.ti --select F

# Run all rules in a subcategory (e.g., all F1xx - Casing rules)
linti process.ti --select F1

# Run multiple rules or groups (comma-separated)
linti process.ti --select F110,S220
linti process.ti --select F,N1,S3

# Combining with other options
linti process.ti --select F --auto-fix
linti process.ti --select N,S --tokens
```

**Selection patterns:**
- `D`, `F`, `N`, `S` – Select all rules in a category
- `D4`, `F1`, `F2`, `F3`, `N1`, `N2`, `S1`, `S2`, `S3` – Select all rules in a subcategory
- `D410`, `F110`, `S220` – Select a specific rule

### Listing Rules

Use the `explain` subcommand to inspect available rules and view detailed guidance for one rule.

```bash
# List all rules with short description and auto-fix support
linti explain

# Explain a specific rule in detail
linti explain F110
```


## Rule Groups

Rules are organized into three main categories, each with a hierarchical numbering scheme. The categorization helps identify the type of violation and group related rules together.

### Format Rules (F1xx, F2xx, F3xx)
Formatting and code style rules:

- **F1xx - Casing**: Keyword capitalization and case consistency
  - `F110` - Keyword Casing
  
- **F2xx - Spacing**: Whitespace and spacing requirements
  - `F220` - Whitespace Around Operators
  - `F230` - Whitespace After Comma
  - `F240` - No Space Before Semicolon
  - `F250` - One Space Inside Parentheses
  - `F260` - No Multiple Spaces
  - `F270` - No Trailing Whitespace
  
- **F3xx - Structure**: Indentation, line breaks, and code layout
  - `F310` - Block Indentation
  - `F320` - One Statement Per Line

### Naming Rules (N1xx, N2xx)
Variable and parameter naming conventions:

- **N1xx - Prefix Naming**: Variable prefix conventions (n, s, c prefixes)
  - `N110` - Variable Prefix Naming
  
- **N2xx - Metadata Naming**: Naming conventions for specific declarations
  - `N210` - Parameter Naming
  - `N220` - Data Source Variable Naming

### Documentation Rules (D4xx)
Documentation and process docstring validation:

- **D4xx - Docstrings**: Required docstring regions and headers
  - `D410` - Docstring Region

### Semantic Rules (S1xx, S2xx, S3xx)
Logic, control flow, and semantic validation:

- **S1xx - Control Flow**: Process execution and control flow patterns
  - `S110` - ProcessQuit Placement
  - `S120` - ItemSkip Block Usage
  
- **S2xx - Immutability**: Variable mutability and assignment constraints
  - `S210` - Read-only Parameters and Variables
  - `S220` - Single-assignment Constants
  
- **S3xx - Security/Calls**: Security-sensitive operations and function calls
  - `S310` - Literal Process Calls
  - `S320` - No ExecuteCommand
  - `S330` - ODBCOpen Password Parameter

Use `linti explain` to list all rules or `linti explain <RULE_ID>` for detailed information about a specific rule.

### Auto-Fix Feature

The linter offers an automatic fix for many rules whenever the fix is safe to apply. In the linting issue report, every issue that can be fixed automatically is marked with a 🔧 indicator, so you can see at a glance which rules will be resolved. Apply the fixes with the `--auto-fix` flag.

## TM1 Block Context Awareness

The linter understands TM1's four execution blocks when procedure sections are available (YAML, Git JSON+TI, PA-code `.ti`, or region-based `.ti`):

- **Prolog**: Initialization and setup code
- **Metadata**: Dimension/hierarchy manipulation code
- **Data**: Record-by-record data processing
- **Epilog**: Finalization and cleanup code

Rules can use block context to enforce block-specific requirements. For example:
- The ProcessQuit rule only allows `ProcessQuit()` in IF/ELSE blocks within Prolog or Epilog
- Rules could require certain variable naming patterns based on the block

Metadata-dependent rules (for example checks based on declared Parameters/Variables)
require formats that provide metadata (`.yaml`, Git JSON+TI, PA-code).

For plain `.ti` files without `#region` sections, the full file is treated as **Prolog**.

## License

This project is licensed under the **Apache License 2.0**. See the [LICENSE](LICENSE) file for details.

The full license text is also available at the [Apache Software Foundation](https://www.apache.org/licenses/LICENSE-2.0).
