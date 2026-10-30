"""Small JSON bridge shared by the browser worker and Pyodide smoke test."""

import json
import warnings
from dataclasses import asdict

from linti.linter.text_api import config_from_text, lint_rule_text, lint_text


def run_linti(source, procedure, rule_id, apply_fix, context_json="{}"):
    context = json.loads(context_json)
    return json.dumps(
        asdict(
            lint_rule_text(
                source,
                procedure,
                rule_id,
                context.get("config", ""),
                auto_fix=apply_fix,
                parameters=context.get("parameters"),
                variables=context.get("variables"),
                datasource_type=context.get("datasource_type"),
                datasource_query=context.get("datasource_query"),
            )
        )
    )


def run_playground(text, config_text, apply_fix):
    """Lint a whole pasted process; see linti.linter.text_api.lint_text.

    Input problems (bad config, unreadable process) come back as a short
    ``error`` message instead of a Python traceback.
    """
    try:
        result = lint_text(text, config_text, auto_fix=apply_fix)
    except (ValueError, OSError) as exc:
        return json.dumps({"error": str(exc)})
    return json.dumps(asdict(result))


def validate_config(config_text):
    """Use the real Core loader before persisting a browser configuration."""
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        try:
            config_from_text(config_text)
        except ValueError as exc:
            return json.dumps({"valid": False, "message": str(exc)})
    return json.dumps({"valid": True, "warnings": [str(item.message) for item in caught]})
