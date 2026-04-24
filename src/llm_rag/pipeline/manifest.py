from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from llm_rag.schemas.provenance import DocumentManifest, FailedStageRecord, ProcessingStage
from llm_rag.utils.hashing import content_hash


def manifest_path(source_path: Path) -> Path:
    """Return the sidecar manifest path for a source file."""
    return source_path.parent / f"{source_path.stem}.manifest.json"


def load_manifest(source_path: Path) -> DocumentManifest | None:
    """Load manifest from disk. Return None if not found."""
    mp = manifest_path(source_path)
    if not mp.exists():
        return None
    return DocumentManifest.model_validate_json(mp.read_text())


def save_manifest(manifest: DocumentManifest) -> None:
    """Save manifest to its sidecar location next to the source file."""
    mp = manifest_path(Path(manifest.source_path))
    mp.write_text(manifest.model_dump_json(indent=2))


def create_manifest(
    source_path: Path,
    doc_id: str,
    doc_type: str,
    source_connector: str,
) -> DocumentManifest:
    """Create a new manifest for a source file."""
    now = datetime.now(timezone.utc)  # noqa: UP017
    return DocumentManifest(
        doc_id=doc_id,
        source_path=str(source_path),
        content_hash=content_hash(source_path),
        doc_type=doc_type,
        source_connector=source_connector,
        fetched_at=now,
        last_processed=now,
    )


def update_stage(manifest: DocumentManifest, stage: ProcessingStage) -> DocumentManifest:
    """Add a processing stage to the manifest. Returns a new manifest (idempotent)."""
    if stage in manifest.stages_completed:
        return manifest
    return manifest.model_copy(
        update={
            "stages_completed": [*manifest.stages_completed, stage],
            "last_processed": datetime.now(timezone.utc),  # noqa: UP017
        }
    )


def mark_stage_failed(
    manifest: DocumentManifest,
    stage: ProcessingStage,
    attempts: int,
    error: str,
) -> DocumentManifest:
    """Record a stage as dead-lettered after exhausting retries.

    Replaces any existing record for the same stage and sets the manifest error field.
    """
    now = datetime.now(timezone.utc)  # noqa: UP017
    record = FailedStageRecord(
        stage=stage,
        attempts=attempts,
        last_error=error,
        failed_at=now,
    )
    # Replace existing record for same stage if present
    existing = [r for r in manifest.failed_stages if r.stage != stage]
    existing.append(record)
    return manifest.model_copy(
        update={
            "failed_stages": existing,
            "error": f"Dead-letter: stage {stage.value} failed after {attempts} attempts: {error}",
            "last_processed": now,
        }
    )


def is_dead_lettered(manifest: DocumentManifest, stage: ProcessingStage) -> bool:
    """Return True if a stage has been dead-lettered."""
    return any(r.stage == stage for r in manifest.failed_stages)


def needs_processing(source_path: Path, stage: ProcessingStage) -> bool:
    """Check if a source file needs processing for a given stage.

    Returns True if:
    - No manifest exists
    - Content hash has changed
    - The stage is not in stages_completed
    Returns False if the stage has been dead-lettered (skip until content changes).
    """
    manifest = load_manifest(source_path)
    if manifest is None:
        return True
    if manifest.content_hash != content_hash(source_path):
        return True
    if is_dead_lettered(manifest, stage):
        return False
    return stage not in manifest.stages_completed
