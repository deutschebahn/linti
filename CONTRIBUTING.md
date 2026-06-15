# Contributing

Thank you for your interest in contributing to Linti!

## Reporting Bugs & Feature Proposals

Please [open a GitHub Issue](https://github.com/your-org/linti/issues) to report bugs or propose new features.

When reporting a bug, please include:

- **Description**: A clear summary of the problem
- **Expected behavior**: What you expected to happen
- **Current behavior**: What actually happens
- **Steps to reproduce**: A minimal example that triggers the issue
- **Environment** (if relevant): OS, Python version, Linti version

## Pull Requests

Pull requests are welcome! For small fixes (typos, minor bugs, documentation) feel free to open a PR directly.

For larger changes — new features, architectural changes, or significant refactors — please **open an issue first** to discuss the approach before writing code. This avoids wasted effort and ensures the change aligns with the project's direction. You are also welcome to indicate in the issue that you intend to implement it yourself.

## Development Setup

1. Clone the repository and change into the project folder.
2. Create a virtual environment: `python -m venv .venv && source .venv/bin/activate`
3. Install the package with dev dependencies: `pip install -e ".[dev]"`
4. Install the pre-commit hooks `pre-commit install`
5. Run the tests: `pytest`

**Optional: Try it out**

6. Run the CLI with the example script: `linti example/example.ti`
   You will see if `example.ti` has got linting issues.
7. Feel free to solve the linting issues in `example.ti` and run `linti example.ti` again to check your fixes.

## Code Style

- Use `ruff` for linting: `ruff check src/`
- After adding or modifying a rule, regenerate `ALL_RULES.md`: `python scripts/generate_all_rules.py`
- Do not edit `ALL_RULES.md` directly.

## License

By contributing, you agree that your contributions will be licensed under the [Apache License 2.0](LICENSE).
