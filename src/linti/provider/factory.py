"""Provider factory for process loading by file path."""

from pathlib import Path

from linti.model.process_ir import ProcessIR
from linti.provider.base import ProcessProvider, load_single_process
from linti.provider.git import GitProvider
from linti.provider.pa_code import PaCodeProvider, is_pa_code_content
from linti.provider.ti import TiProvider
from linti.provider.yaml_ti import YamlProvider

PA_DETECTION_PEEK_BYTES = 32 * 1024


def _peek_pa_detection_text(file_path: Path) -> str:
    """Read only head/tail chunks for PA-code marker detection."""
    try:
        with file_path.open("rb") as f:
            head = f.read(PA_DETECTION_PEEK_BYTES)
            f.seek(0, 2)
            size = f.tell()
            if size <= PA_DETECTION_PEEK_BYTES:
                return head.decode("utf-8", errors="ignore")

            tail_start = max(size - PA_DETECTION_PEEK_BYTES, 0)
            f.seek(tail_start)
            tail = f.read(PA_DETECTION_PEEK_BYTES)
    except OSError:
        return ""

    return (
        head.decode("utf-8", errors="ignore")
        + "\n"
        + tail.decode("utf-8", errors="ignore")
    )


def provider_for_path(file_path: Path) -> ProcessProvider:
    """Return the provider implementation for *file_path*."""
    suffix = file_path.suffix.lower()
    if suffix in (".yaml", ".yml"):
        return YamlProvider(file_path)
    if suffix == ".json":
        return GitProvider(file_path)
    if suffix == ".ti":
        # Check for a sibling JSON file (Git-deploy format).
        json_sibling = file_path.with_suffix(".json")
        if json_sibling.exists():
            return GitProvider(json_sibling)

        # Check for PA code format (#SECTION + #JSON_PROPERTIES).
        if is_pa_code_content(_peek_pa_detection_text(file_path)):
            return PaCodeProvider(file_path)

        return TiProvider(file_path)
    raise ValueError(
        f"No loader registered for file type: {file_path.suffix!r} ({file_path})"
    )


def load_process(file_path: Path) -> ProcessIR:
    """Load a TM1 process from *file_path* using the appropriate provider."""
    return load_single_process(provider_for_path(file_path))
