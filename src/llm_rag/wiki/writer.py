from __future__ import annotations

import re
from pathlib import Path

_SOURCE_VARIANT_BASES = {"evidence"}
_DEFAULT_SOURCE = "literature"


def _resolve_section_name(name: str) -> tuple[str, str]:
    """Return (target_name, legacy_name) for a section update."""
    if name in _SOURCE_VARIANT_BASES:
        return f"{name}-{_DEFAULT_SOURCE}", name
    return name, name


def update_auto_sections(path: Path, sections: dict[str, str]) -> None:
    """Replace content inside auto-fenced sections. Human sections are untouched."""
    content = path.read_text()
    for raw_name, new_content in sections.items():
        name, legacy_name = _resolve_section_name(raw_name)
        stripped = new_content.strip()
        body = f"\n{stripped}\n" if stripped else "\n"

        def _repl(m: re.Match[str], _body: str = body) -> str:
            return f"{m.group(1)}{_body}{m.group(2)}"

        updated = re.sub(
            rf"(<!-- auto-start: {re.escape(name)} -->).*?(<!-- auto-end: {re.escape(name)} -->)",
            _repl,
            content,
            flags=re.DOTALL,
        )
        if updated == content and legacy_name != name:
            updated = re.sub(
                rf"(<!-- auto-start: {re.escape(legacy_name)} -->).*?(<!-- auto-end: {re.escape(legacy_name)} -->)",
                _repl,
                content,
                flags=re.DOTALL,
            )
        content = updated
    path.write_text(content)


def create_page(path: Path, template: str, substitutions: dict[str, str]) -> None:
    """Render template with substitutions and write to path. No-op if path exists."""
    if path.exists():
        return
    content = template
    for key, value in substitutions.items():
        content = content.replace(f"{{{{ {key} }}}}", value)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
