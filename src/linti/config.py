"""Configuration loader for linti."""

import warnings
from pathlib import Path
from typing import Literal, Optional

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator


class LintiConfigWarning(UserWarning):
    """Warning about a linti config file (removed/moved/deprecated settings).

    A dedicated category so the CLI can render these cleanly while non-linti
    warnings keep their default formatting.
    """


class ConflictingGenericPrefixesError(ValueError):
    """Raised when generic_prefixes is set both at the top level and via a
    deprecated per-rule setting.

    There is no sensible precedence to fall back to here: silently picking
    one side would hide a config mistake, so loading fails instead.
    """


_REMOVED_RULE_CONFIGS = {
    "one_space_before_equals": (
        "Configures the removed Equals Spacing rule. "
        "This setting is ignored; remove 'rules.one_space_before_equals' from the config."
    ),
    "process_quit": (
        "The 'process_quit' rule was renamed. This setting is ignored; use "
        "'rules.conditional_control_flow' (and 'rules.unreachable_code') instead."
    ),
}

# Per-rule settings that have moved to a top-level config key. Maps the rule
# config key to the (old setting, new top-level setting) pair.
_MOVED_TO_TOPLEVEL = {
    "docstring_region": ("generic_prefixes", "generic_prefixes"),
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


class ConditionalControlFlowConfig(BaseModel):
    """Configuration for ConditionalControlFlowRule."""

    enabled: bool = True


class UnreachableCodeConfig(BaseModel):
    """Configuration for UnreachableCodeRule."""

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


class HardcodedSecretConfig(BaseModel):
    """Configuration for HardcodedSecretRule (X130)."""

    enabled: bool = True
    # Which preset of secret-looking name fragments to match. `custom` starts
    # from an empty preset, so `secret_names` becomes the whole list.
    mode: Literal["relaxed", "standard", "strict", "custom"] = "standard"
    # Extra name fragments, matched case-insensitively as substrings. Added on
    # top of the preset selected by `mode`.
    secret_names: list[str] = Field(default_factory=list)
    # Whether reading a secret out of a cube (CellGetS, AttrS, …) is accepted.
    # Off by default: the TM1 data directory can be encrypted but rarely is.
    allow_secrets_in_cubes: bool = False


class UseHierarchyAwareFunctionsConfig(BaseModel):
    """Configuration for UseHierarchyAwareFunctionsRule (C410)."""

    enabled: bool = True
    mode: Literal["enforce", "consistent"] = "consistent"
    # Generic processes are taken from the top-level `generic_prefixes` setting.


class DoNotUseUndocumentedFunctionsConfig(BaseModel):
    """Configuration for DoNotUseUndocumentedFunctionsRule (C430)."""

    enabled: bool = True
    # Undocumented functions the project knowingly relies on; matched
    # case-insensitively and never reported.
    allowed_functions: list[str] = Field(default_factory=list)


class FunctionVersionCompatibilityConfig(BaseModel):
    """Configuration for FunctionVersionCompatibilityRule (C510)."""

    # Opt-in: the target version depends on the deployment strategy.
    enabled: bool = False
    # Per-rule override of the top-level `target_version`. Left unset (None), the
    # rule inherits the top-level value; an explicit value here wins.
    mode: Optional[Literal["CompatibleWithV11AndV12", "V11", "V12"]] = None
    # The same override in the top-level vocabulary. Declared so that writing it
    # here — the natural mistake, given the key exists at top level — is honoured
    # rather than silently dropped by pydantic. `mode` wins if both are set.
    target_version: Optional[Literal["v11", "v12", "both"]] = None


class NewLinePerStatementConfig(BaseModel):
    """Configuration for NewLinePerStatementRule."""

    enabled: bool = True


class DocstringRegionConfig(BaseModel):
    """Configuration for DocstringRegionRule (D110)."""

    enabled: bool = False
    region_name: str = "Docstring"
    required_headers: list[str] = Field(default_factory=lambda: ["# Description"])
    # Deprecated: use the top-level `generic_prefixes` instead. Still honoured
    # (and overrides the top-level value) while present.
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
    conditional_control_flow: ConditionalControlFlowConfig = Field(
        default_factory=ConditionalControlFlowConfig
    )
    unreachable_code: UnreachableCodeConfig = Field(
        default_factory=UnreachableCodeConfig
    )
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
    hardcoded_secret: HardcodedSecretConfig = Field(
        default_factory=HardcodedSecretConfig
    )
    use_hierarchy_aware_functions: UseHierarchyAwareFunctionsConfig = Field(
        default_factory=UseHierarchyAwareFunctionsConfig
    )
    do_not_use_undocumented_functions: DoNotUseUndocumentedFunctionsConfig = Field(
        default_factory=DoNotUseUndocumentedFunctionsConfig
    )
    function_version_compatibility: FunctionVersionCompatibilityConfig = Field(
        default_factory=FunctionVersionCompatibilityConfig
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
    # Names starting with one of these prefixes mark a *generic* (templated)
    # process. Rules that treat generic processes specially (D110, C410) share
    # this single definition.
    generic_prefixes: list[str] = Field(default_factory=list)
    # Files, directories, or glob patterns to skip during discovery. CLI
    # ``--exclude-path`` values extend (never replace) this list.
    exclude_paths: list[str] = Field(default_factory=list)
    # Target Planning Analytics / TM1 version the code must run on. A project-wide
    # fact shared by version-aware rules (currently C510); left unset (None) the
    # rules fall back to their own default. `both` == must run on v11 and v12.
    target_version: Optional[Literal["v11", "v12", "both"]] = None
    # Input-hardening limits (defend against pathological / untrusted input).
    # Control-flow nesting beyond this depth yields an S900 diagnostic instead
    # of recursing until a RecursionError.
    max_nesting_depth: int = Field(default=150)
    # Files larger than this (bytes) are rejected before being read into memory.
    max_file_size: int = Field(default=10 * 1024 * 1024)  # 10 MB
    # Cap on how many distinct values the constant evaluation index keeps per
    # variable (e.g. across IF/ELSE branches) before degrading to UNKNOWN.
    max_values_per_variable: int = Field(default=8)

    @model_validator(mode="after")
    def _check_conflicting_generic_prefixes(self) -> "Config":
        """Reject configs setting generic_prefixes both top-level and per-rule.

        The per-rule setting is deprecated and going away; rather than pick a
        side (and risk silently ignoring one of them), fail with guidance to
        remove the deprecated key.
        """
        if not self.generic_prefixes:
            return self

        for rule_key, (old_key, new_key) in _MOVED_TO_TOPLEVEL.items():
            rule_cfg = getattr(self.rules, rule_key, None)
            if rule_cfg is not None and getattr(rule_cfg, old_key, None):
                raise ConflictingGenericPrefixesError(
                    f"Both the top-level '{new_key}' and the deprecated "
                    f"'rules.{rule_key}.{old_key}' are set. Remove "
                    f"'rules.{rule_key}.{old_key}' from linti.yaml and keep "
                    f"only the top-level '{new_key}' setting."
                )
        return self

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
                    LintiConfigWarning,
                    stacklevel=2,
                )

    @staticmethod
    def _warn_about_moved_rule_configs(config_dict: dict, config_path: Path) -> None:
        """Warn when a setting still lives under a rule but moved to top level."""
        rules_cfg = config_dict.get("rules")
        if not isinstance(rules_cfg, dict):
            return

        for rule_key, (old_key, new_key) in _MOVED_TO_TOPLEVEL.items():
            rule_cfg = rules_cfg.get(rule_key)
            uses_deprecated_key = isinstance(rule_cfg, dict) and rule_cfg.get(old_key)
            both_set = uses_deprecated_key and config_dict.get(new_key)
            if not uses_deprecated_key or both_set:
                # Nothing to warn about, or Config's validator raises for the
                # conflicting case instead of also warning here.
                continue

            warnings.warn(
                f"{config_path}: 'rules.{rule_key}.{old_key}' is deprecated; "
                f"move it to the top-level '{new_key}' setting. The per-rule "
                "value is still honoured for now.",
                LintiConfigWarning,
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
        cls._warn_about_moved_rule_configs(config_dict, config_path)

        return cls(**config_dict)

    @classmethod
    def find_config_file(cls, target_file: Path) -> Optional[Path]:
        """Locate the ``linti.yaml`` that governs *target_file*, if any.

        Walks upward from *target_file*'s directory, stopping at the first
        ``linti.yaml`` (returned), at a project root marker
        (``.git``, ``pyproject.toml``, ``setup.cfg``, ``setup.py``), or at the
        filesystem root. The project-root boundary prevents accidentally
        picking up a stray config file from a parent outside the project tree.

        Returns the config file path, or ``None`` when none is found within the
        project boundary.
        """
        directory = target_file.parent.resolve()

        while True:
            config_file = directory / "linti.yaml"
            if config_file.exists():
                return config_file

            # Stop if this directory is a project root.
            if any((directory / marker).exists() for marker in _PROJECT_ROOT_MARKERS):
                return None

            parent = directory.parent
            if parent == directory:
                # Reached filesystem root
                return None
            directory = parent

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
        config_file = cls.find_config_file(target_file)
        if config_file is None:
            return cls()
        try:
            return cls.load_from_file(config_file)
        except Exception as e:
            raise ValueError(f"Failed to load config from {config_file}: {e}") from e
