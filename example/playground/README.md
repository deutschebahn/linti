# Playground example

These four files are the same short TI process in the formats accepted by the
browser playground. The site imports them directly; keep the Prolog code in sync
when changing the example.

- `process.ti`: plain TI (all code is Prolog)
- `process-regions.ti`: TI with `#region` sections
- `process-pa.ti`: PA code with `#SECTION` and `#JSON_PROPERTIES`
- `process.yaml`: TM1py process YAML

The mistakes are intentional: inconsistent keyword casing, spacing around
operators and function arguments, missing spaces after commas, a numeric
variable without the `n` prefix, and reassignment of a constant.
