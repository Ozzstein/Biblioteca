from __future__ import annotations

import re
from pathlib import Path


def update_auto_sections(path: Path, sections: dict[str, str]) -> None:
    """Replace content inside auto-fenced sections. Human sections are untouched."""
    content = path.read_text()
    for name, new_content in sections.items():
        stripped = new_content.strip()
        body = f"\n{stripped}\n" if stripped else "\n"

        def _repl(m: re.Match[str], _body: str = body) -> str:
            return f"{m.group(1)}{_body}{m.group(2)}"

        content = re.sub(
            rf"(<!-- auto-start: {re.escape(name)} -->).*?(<!-- auto-end: {re.escape(name)} -->)",
            _repl,
            content,
            flags=re.DOTALL,
        )
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
