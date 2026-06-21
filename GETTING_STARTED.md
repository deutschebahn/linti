# Getting Started

Use this quick guide to run linti on your first TM1 process file.

Before you start, make sure you have at least one supported process file.
See supported formats in [README.md](README.md#supported-input-formats).

## 1. Install Python

Install Python 3.10 or higher and verify it is available in your terminal.

```bash
python --version
```

## 2. Install linti via pip

```bash
pip install linti
```

## 3. Run linti on your file

```bash
linti my-process.ti
```

You can also lint other supported formats (YAML, Git JSON+TI, PA-code `.ti`) listed in the README.

## 4. Auto-fix or customize rules

Try auto-fix:

```bash
linti my-process.ti --auto-fix
```

Or if you are not happy with the linting issues, create a `linti.yaml` and configure your preferred rules and settings.

For full rule explanations and configuration examples, see [ALL_RULES.md](ALL_RULES.md).

Example:

```yaml
rules:
  keyword_casing:
    enabled: true
    style: uppercase
  indentation:
    enabled: true
    size: 4
  variable_prefix:
    enabled: true
    allow_constant_prefix: false
```

Then run again:

```bash
linti my-process.ti --config linti.yaml
```
