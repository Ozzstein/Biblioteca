from __future__ import annotations

import json
import re
from pathlib import Path


def test_api_spec_json_examples_parse() -> None:
    spec = Path("docs/api/v1.md").read_text()
    blocks = re.findall(r"```json\n(.*?)\n```", spec, flags=re.DOTALL)

    assert blocks
    for block in blocks:
        json.loads(block)
