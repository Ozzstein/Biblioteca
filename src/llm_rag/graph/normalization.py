"""Entity normalization: alias resolution, canonical ID generation, and name normalization."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]


def load_normalization_map(yaml_path: Path) -> dict[str, str]:
    """Load entity-normalization.yaml and return a mapping of alias -> canonical entity_id.

    Args:
        yaml_path: Path to entity-normalization.yaml.

    Returns:
        Dict mapping each known alias (lowercased) to its canonical entity_id.
    """
    if not yaml_path.exists():
        return {}
    data: dict[str, Any] = yaml.safe_load(yaml_path.read_text()) or {}
    alias_map: dict[str, str] = {}
    for section in data.values():
        if not isinstance(section, dict):
            continue
        for entry in section.values():
            if not isinstance(entry, dict):
                continue
            entity_id = entry.get("entity_id")
            if not entity_id:
                continue
            for alias in entry.get("aliases", []):
                alias_map[alias.lower()] = str(entity_id)
    return alias_map


def resolve_alias(alias: str, yaml_path: Path) -> str | None:
    """Look up an alias in entity-normalization.yaml and return the canonical entity_id.

    The lookup is case-insensitive.

    Args:
        alias: The alias string to resolve.
        yaml_path: Path to entity-normalization.yaml.

    Returns:
        The canonical entity_id, or None if not found.
    """
    alias_map = load_normalization_map(yaml_path)
    return alias_map.get(alias.lower())


_SLUG_RE = re.compile(r"[^a-z0-9]+")


def canonical_entity_id(entity_type: str, name: str) -> str:
    """Generate a canonical entity ID from an entity type and name.

    Produces IDs in the form ``<type>:<slug>`` where slug is lowercased,
    whitespace/special-chars collapsed to hyphens, and leading/trailing hyphens stripped.

    Examples:
        >>> canonical_entity_id("Material", "LiFePO4")
        'material:lifepo4'
        >>> canonical_entity_id("FailureMechanism", "SEI Growth")
        'failuremechanism:sei-growth'

    Args:
        entity_type: The entity type string (e.g. "Material", "Process").
        name: The human-readable entity name.

    Returns:
        A stable, slug-form entity ID.
    """
    type_slug = entity_type.lower()
    name_slug = _SLUG_RE.sub("-", name.lower()).strip("-")
    return f"{type_slug}:{name_slug}"


def normalize_entity_id(entity_id: str, alias_map: dict[str, str]) -> str:
    """Resolve an entity_id through the alias map, returning the canonical ID.

    Checks the full entity_id, the name portion (after the colon), and the
    original string against the alias map.  Also tries normalizing hyphens to
    spaces in the name portion since aliases often use spaces while entity IDs
    use hyphens. Returns the first match found, or the original entity_id if
    no alias applies.

    Args:
        entity_id: The entity ID to resolve (e.g. ``"material:lifepo4"``).
        alias_map: Mapping of lowercased alias -> canonical entity_id,
            as returned by :func:`load_normalization_map`.

    Returns:
        The canonical entity_id if a match is found, otherwise the input unchanged.
    """
    lowered = entity_id.lower()
    if lowered in alias_map:
        return alias_map[lowered]
    # Try just the name portion (after the colon)
    if ":" in entity_id:
        name_part = entity_id.split(":", 1)[1]
        if name_part.lower() in alias_map:
            return alias_map[name_part.lower()]
        # Also try with hyphens replaced by spaces (common normalization gap)
        name_with_spaces = name_part.replace("-", " ").lower()
        if name_with_spaces in alias_map:
            return alias_map[name_with_spaces]
    return entity_id


def canonicalize_relation_endpoints(
    source_id: str,
    target_id: str,
    alias_map: dict[str, str],
) -> tuple[str, str]:
    """Rewrite both ends of a relation to canonical entity IDs.

    Args:
        source_id: The source entity ID of the relation.
        target_id: The target entity ID of the relation.
        alias_map: Alias -> canonical ID mapping.

    Returns:
        A ``(canonical_source, canonical_target)`` tuple.
    """
    return normalize_entity_id(source_id, alias_map), normalize_entity_id(target_id, alias_map)


def normalize_entity_name(name: str) -> str:
    """Normalize an entity name for comparison by lowercasing and collapsing whitespace.

    Args:
        name: Raw entity name string.

    Returns:
        Normalized name suitable for deduplication comparisons.
    """
    return " ".join(name.lower().split())
