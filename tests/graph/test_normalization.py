from __future__ import annotations

from pathlib import Path

import pytest

from llm_rag.graph.normalization import (
    canonical_entity_id,
    canonicalize_relation_endpoints,
    load_normalization_map,
    normalize_entity_id,
    normalize_entity_name,
    resolve_alias,
)

SAMPLE_YAML = """\
materials:
  LFP:
    entity_id: "material:lfp"
    aliases:
      - LiFePO4
      - lithium iron phosphate
  NMC811:
    entity_id: "material:nmc811"
    aliases:
      - NMC 811
      - NCM811
processes:
  calcination:
    entity_id: "process:calcination"
    aliases:
      - sintering
      - heat treatment
"""


@pytest.fixture()
def norm_yaml(tmp_path: Path) -> Path:
    p = tmp_path / "entity-normalization.yaml"
    p.write_text(SAMPLE_YAML)
    return p


class TestLoadNormalizationMap:
    def test_loads_aliases_lowercased(self, norm_yaml: Path) -> None:
        alias_map = load_normalization_map(norm_yaml)
        assert alias_map["lifepo4"] == "material:lfp"
        assert alias_map["lithium iron phosphate"] == "material:lfp"
        assert alias_map["nmc 811"] == "material:nmc811"
        assert alias_map["sintering"] == "process:calcination"

    def test_returns_empty_for_missing_file(self, tmp_path: Path) -> None:
        alias_map = load_normalization_map(tmp_path / "nonexistent.yaml")
        assert alias_map == {}

    def test_returns_empty_for_empty_file(self, tmp_path: Path) -> None:
        p = tmp_path / "empty.yaml"
        p.write_text("")
        alias_map = load_normalization_map(p)
        assert alias_map == {}


class TestResolveAlias:
    def test_resolves_known_alias(self, norm_yaml: Path) -> None:
        assert resolve_alias("LiFePO4", norm_yaml) == "material:lfp"

    def test_case_insensitive(self, norm_yaml: Path) -> None:
        assert resolve_alias("lifepo4", norm_yaml) == "material:lfp"
        assert resolve_alias("LIFEPO4", norm_yaml) == "material:lfp"

    def test_returns_none_for_unknown(self, norm_yaml: Path) -> None:
        assert resolve_alias("unknown-material", norm_yaml) is None

    def test_returns_none_for_missing_file(self, tmp_path: Path) -> None:
        assert resolve_alias("LiFePO4", tmp_path / "nope.yaml") is None


class TestCanonicalEntityId:
    def test_simple_material(self) -> None:
        assert canonical_entity_id("Material", "LFP") == "material:lfp"

    def test_multi_word_name(self) -> None:
        assert canonical_entity_id("FailureMechanism", "SEI Growth") == "failuremechanism:sei-growth"

    def test_special_chars_collapsed(self) -> None:
        assert canonical_entity_id("Process", "coin cell  assembly!") == "process:coin-cell-assembly"

    def test_formula_preserved(self) -> None:
        assert canonical_entity_id("Material", "LiFePO4") == "material:lifepo4"

    def test_strips_leading_trailing_hyphens(self) -> None:
        assert canonical_entity_id("Material", " -LFP- ") == "material:lfp"


class TestNormalizeEntityId:
    def test_resolves_alias_by_name_part(self, norm_yaml: Path) -> None:
        alias_map = load_normalization_map(norm_yaml)
        assert normalize_entity_id("material:lifepo4", alias_map) == "material:lfp"

    def test_resolves_alias_by_full_id(self, norm_yaml: Path) -> None:
        alias_map = load_normalization_map(norm_yaml)
        # "sintering" is a known alias
        assert normalize_entity_id("sintering", alias_map) == "process:calcination"

    def test_returns_original_when_no_match(self, norm_yaml: Path) -> None:
        alias_map = load_normalization_map(norm_yaml)
        assert normalize_entity_id("process:unknown", alias_map) == "process:unknown"

    def test_case_insensitive(self, norm_yaml: Path) -> None:
        alias_map = load_normalization_map(norm_yaml)
        assert normalize_entity_id("material:LiFePO4", alias_map) == "material:lfp"


class TestCanonicalizeRelationEndpoints:
    def test_rewrites_both_endpoints(self, norm_yaml: Path) -> None:
        alias_map = load_normalization_map(norm_yaml)
        src, tgt = canonicalize_relation_endpoints(
            "material:lifepo4", "material:ncm811", alias_map,
        )
        assert src == "material:lfp"
        assert tgt == "material:nmc811"

    def test_preserves_unknown_endpoints(self, norm_yaml: Path) -> None:
        alias_map = load_normalization_map(norm_yaml)
        src, tgt = canonicalize_relation_endpoints(
            "process:unknown", "metric:capacity", alias_map,
        )
        assert src == "process:unknown"
        assert tgt == "metric:capacity"

    def test_mixed_known_and_unknown(self, norm_yaml: Path) -> None:
        alias_map = load_normalization_map(norm_yaml)
        src, tgt = canonicalize_relation_endpoints(
            "material:lifepo4", "metric:capacity", alias_map,
        )
        assert src == "material:lfp"
        assert tgt == "metric:capacity"


class TestNormalizeEntityName:
    def test_lowercases(self) -> None:
        assert normalize_entity_name("LiFePO4") == "lifepo4"

    def test_collapses_whitespace(self) -> None:
        assert normalize_entity_name("  NMC   811  ") == "nmc 811"

    def test_preserves_internal_structure(self) -> None:
        assert normalize_entity_name("solid electrolyte interphase") == "solid electrolyte interphase"
