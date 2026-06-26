"""Configuration loader for linti."""

import warnings
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

_REMOVED_RULE_CONFIGS = {
    "one_space_before_equals": (
        "Configures removed rule F210 (Equals Spacing). "
        "This setting is ignored; remove 'rules.one_space_before_equals' from the config."
    )
}


class KeywordCasingConfig(BaseModel):
    """Configuration for KeywordCasingRule."""

    enabled: bool = True
    style: Literal["uppercase", "lowercase", "camelcase", "consistent"] = "uppercase"


class IndentationConfig(BaseModel):
    """Configuration for IndentationRule."""

    enabled: bool = True
    size: int = 4


class VariablePrefixConfig(BaseModel):
    """Configuration for VariablePrefixRule."""

    enabled: bool = True
    allow_constant_prefix: bool = False


class ProcessQuitConfig(BaseModel):
    """Configuration for ProcessQuitRule."""

    enabled: bool = True


class ItemSkipConfig(BaseModel):
    """Configuration for ItemSkipRule."""

    enabled: bool = True


class EmptyBlockConfig(BaseModel):
    """Configuration for EmptyBlockRule."""

    enabled: bool = True


class ParameterNamingConfig(BaseModel):
    """Configuration for ParameterNamingRule."""

    enabled: bool = True


class VariableNamingConfig(BaseModel):
    """Configuration for VariableNamingRule."""

    enabled: bool = True


class ReadOnlyParameterVariableConfig(BaseModel):
    """Configuration for ReadOnlyParameterVariableRule."""

    enabled: bool = True


class ProcessCallLiteralConfig(BaseModel):
    """Configuration for ProcessCallLiteralRule."""

    enabled: bool = True


class ExecuteCommandConfig(BaseModel):
    """Configuration for ExecuteCommandRule."""

    enabled: bool = True


class ODBCOpenParameterConfig(BaseModel):
    """Configuration for ODBCOpenParameterRule."""

    enabled: bool = True


class NewLinePerStatementConfig(BaseModel):
    """Configuration for NewLinePerStatementRule."""

    enabled: bool = True


class DocstringRegionConfig(BaseModel):
    """Configuration for DocstringRegionRule (D410)."""

    enabled: bool = False
    region_name: str = "Docstring"
    required_headers: list[str] = Field(default_factory=lambda: ["# Description"])
    generic_prefixes: list[str] = Field(default_factory=list)
    generic_extra_headers: list[str] = Field(default_factory=lambda: ["# Use Case"])


class WhitespaceConfig(BaseModel):
    """Configuration for the whitespace rule group (W101-W106)."""

    enabled: bool = True
    around_operators: bool = True
    after_comma: bool = True
    no_space_before_semicolon: bool = True
    one_space_inside_parentheses: bool = True
    no_multiple_spaces: bool = True
    no_trailing_whitespace: bool = True


class RulesConfig(BaseModel):
    """Configuration for all linting rules.

    Known rules have typed fields for validation.  Unknown keys are accepted
    via ``extra = "allow"`` so that new rules only need a rule file — no
    Config class or RulesConfig field required.
    """

    model_config = ConfigDict(extra="allow")

    keyword_casing: KeywordCasingConfig = Field(default_factory=KeywordCasingConfig)
    indentation: IndentationConfig = Field(default_factory=IndentationConfig)
    variable_prefix: VariablePrefixConfig = Field(default_factory=VariablePrefixConfig)
    process_quit: ProcessQuitConfig = Field(default_factory=ProcessQuitConfig)
    item_skip: ItemSkipConfig = Field(default_factory=ItemSkipConfig)
    empty_block: EmptyBlockConfig = Field(default_factory=EmptyBlockConfig)
    parameter_naming: ParameterNamingConfig = Field(
        default_factory=ParameterNamingConfig
    )
    variable_naming: VariableNamingConfig = Field(default_factory=VariableNamingConfig)
    readonly_parameter_variable: ReadOnlyParameterVariableConfig = Field(
        default_factory=ReadOnlyParameterVariableConfig
    )
    process_call_literal: ProcessCallLiteralConfig = Field(
        default_factory=ProcessCallLiteralConfig
    )
    execute_command: ExecuteCommandConfig = Field(default_factory=ExecuteCommandConfig)
    odbc_open_parameter: ODBCOpenParameterConfig = Field(
        default_factory=ODBCOpenParameterConfig
    )
    newline_per_statement: NewLinePerStatementConfig = Field(
        default_factory=NewLinePerStatementConfig
    )
    docstring_region: DocstringRegionConfig = Field(
        default_factory=DocstringRegionConfig
    )
    whitespace: WhitespaceConfig = Field(default_factory=WhitespaceConfig)


# Markers that indicate a project root directory.
_PROJECT_ROOT_MARKERS = (".git", "pyproject.toml", "setup.cfg", "setup.py")


class Config(BaseModel):
    """Configuration for linti."""

    rules: RulesConfig = Field(default_factory=RulesConfig)

    @staticmethod
    def _warn_about_removed_rule_configs(config_dict: dict, config_path: Path) -> None:
        """Warn when a config still references removed rules."""
        rules_cfg = config_dict.get("rules")
        if not isinstance(rules_cfg, dict):
            return

        for key, message in _REMOVED_RULE_CONFIGS.items():
            if key in rules_cfg:
                warnings.warn(
                    f"{config_path}: {message}",
                    UserWarning,
                    stacklevel=2,
                )

    @classmethod
    def load_from_file(cls, config_path: Path) -> "Config":
        """
        Load configuration from a YAML file.

        Args:
            config_path: Path to the configuration file.

        Returns:
            Config instance with loaded settings.

        Raises:
            FileNotFoundError: If config file doesn't exist.
            ValueError: If yaml is not installed or file is invalid.
        """
        if not config_path.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")

        with open(config_path, "r") as f:
            config_dict = yaml.safe_load(f) or {}

        cls._warn_about_removed_rule_configs(config_dict, config_path)

        return cls(**config_dict)

    @classmethod
    def find_and_load(cls, target_file: Path) -> "Config":
        """
        Search for linti.yaml starting from *target_file*'s directory
        and walking upward until a project root is reached.

        The search stops when:
        - a ``linti.yaml`` is found (loaded and returned), **or**
        - the current directory contains a project root marker
          (``.git``, ``pyproject.toml``, ``setup.cfg``, ``setup.py``), **or**
        - the filesystem root is reached.

        This prevents accidentally picking up a stray config file from
        a parent outside the project tree.

        Args:
            target_file: Path to the file being linted.

        Returns:
            Config instance with loaded settings, or default Config if
            no config file is found within the project boundary.
        """
        directory = target_file.parent.resolve()

        while True:
            config_file = directory / "linti.yaml"
            if config_file.exists():
                try:
                    return cls.load_from_file(config_file)
                except Exception as e:
                    raise ValueError(
                        f"Failed to load config from {config_file}: {e}"
                    ) from e

            # Stop if this directory is a project root.
            if any((directory / marker).exists() for marker in _PROJECT_ROOT_MARKERS):
                break

            parent = directory.parent
            if parent == directory:
                # Reached filesystem root
                break
            directory = parent

        return cls()
