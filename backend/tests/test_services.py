from __future__ import annotations

import json
from pathlib import Path
import shutil

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.config import Settings
from app.database import Base
from app.models import MatchStatus, SelectionCandidate, SelectionStatus
from app.services import (
    CopyConflictError,
    copy_candidate_files,
    discover_files,
    finalize_copies,
    match_by_filename,
    match_by_json_key,
    resolve_safe,
    scan_candidates,
)


@pytest.fixture
def roots(tmp_path: Path):
    paths = {
        "raw": tmp_path / "dataset/source-data",
        "labeled": tmp_path / "dataset/label-data",
        "selected": tmp_path / "selected",
        "app-data": tmp_path / "app-data",
    }
    for path in paths.values():
        path.mkdir(parents=True)
    settings = Settings(
        data_root_path=tmp_path,
        selected_data_path=paths["selected"],
        app_data_path=paths["app-data"],
    )
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return paths, settings, sessionmaker(engine, expire_on_commit=False)


def write(path: Path, content: str = "data") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_filename_matching_groups_multiple_source_files_and_detects_conflict(roots):
    paths, _, _ = roots
    write(paths["raw"] / "region/images/scene.png")
    write(paths["raw"] / "region/images/scene.pcd")
    write(paths["labeled"] / "labels/scene.json", "{}")

    matched = match_by_filename(discover_files(paths["raw"]), discover_files(paths["labeled"], label_only=True))
    assert matched[0].status == MatchStatus.MATCHED
    assert [item.extension for item in matched[0].raw_files] == [".pcd", ".png"]

    write(paths["raw"] / "other/scene.png")
    conflicted = match_by_filename(discover_files(paths["raw"]), discover_files(paths["labeled"], label_only=True))
    assert conflicted[0].status == MatchStatus.CONFLICT


def test_json_key_resolves_multiple_references_and_reports_bad_json(roots):
    paths, _, _ = roots
    write(paths["raw"] / "region/images/a.png")
    write(paths["raw"] / "region/objects/a.pcd")
    write(paths["labeled"] / "labels/a.json", json.dumps({"sources": ["region/images/a.png", "region/objects/a.pcd"]}))
    write(paths["labeled"] / "labels/b.json", "{")

    results = match_by_json_key(discover_files(paths["raw"]), discover_files(paths["labeled"], label_only=True), "sources")
    assert results[0].status == MatchStatus.MATCHED
    assert [item.relative for item in results[0].raw_files] == ["region/images/a.png", "region/objects/a.pcd"]
    assert results[1].status == MatchStatus.ERROR


def test_json_single_filename_represents_same_stem_source_bundle(roots):
    paths, _, _ = roots
    write(paths["raw"] / "images/scene.png")
    write(paths["raw"] / "objects/scene.pcd")
    write(paths["labeled"] / "scene.json", json.dumps({"data_key": "scene.png"}))
    results = match_by_json_key(
        discover_files(paths["raw"]), discover_files(paths["labeled"], label_only=True), "data_key"
    )
    assert results[0].status == MatchStatus.MATCHED
    assert {item.extension for item in results[0].raw_files} == {".png", ".pcd"}


def test_scan_is_idempotent_and_copy_preserves_sources_and_relative_paths(roots):
    paths, settings, session_factory = roots
    write(paths["raw"] / "region/images/scene.png")
    write(paths["raw"] / "region/images/scene.pcd")
    write(paths["labeled"] / "region/labels/scene.json", "{}")

    with session_factory() as db:
        first = scan_candidates(db, settings, "file_name", "data_key", paths["raw"], paths["labeled"])
        second = scan_candidates(db, settings, "file_name", "data_key", paths["raw"], paths["labeled"])
        assert first["created"] == 1
        assert second["created"] == 0
        assert second["updated"] == 1
        assert len(db.scalars(select(SelectionCandidate)).all()) == 1

        candidate = db.scalar(select(SelectionCandidate))
        copied = copy_candidate_files(candidate, settings, paths["raw"], paths["labeled"])
        candidate.selection_status = SelectionStatus.SELECTED
        db.commit()

        assert len(copied) == 3
        assert (paths["raw"] / "region/images/scene.png").is_file()
        assert (paths["raw"] / "region/images/scene.pcd").is_file()
        assert (paths["labeled"] / "region/labels/scene.json").is_file()
        assert (paths["selected"] / "dataset/source-data/region/images/scene.png").is_file()
        assert (paths["selected"] / "dataset/source-data/region/images/scene.pcd").is_file()
        assert (paths["selected"] / "dataset/label-data/region/labels/scene.json").is_file()


def test_copy_preflight_collision_does_not_modify_any_source(roots):
    paths, settings, session_factory = roots
    raw = paths["raw"] / "nested/scene.png"
    label = paths["labeled"] / "nested/scene.json"
    write(raw)
    write(label, "{}")

    with session_factory() as db:
        scan_candidates(db, settings, "file_name", "data_key", paths["raw"], paths["labeled"])
        candidate = db.scalar(select(SelectionCandidate))
        destination = paths["selected"] / "dataset/label-data/nested/scene.json"
        write(destination, "collision")
        with pytest.raises(CopyConflictError) as conflict:
            copy_candidate_files(candidate, settings, paths["raw"], paths["labeled"])
        assert conflict.value.conflicts == ["dataset/label-data/nested/scene.json"]
        assert raw.is_file()
        assert label.is_file()
        copied = copy_candidate_files(candidate, settings, paths["raw"], paths["labeled"], overwrite=True)
        finalize_copies(copied)
        assert destination.read_text(encoding="utf-8") == "{}"
        assert not list(destination.parent.glob(".scene.json.prework-*.bak"))


def test_copy_retry_reuses_matching_partial_file_from_previous_move_failure(roots):
    paths, settings, session_factory = roots
    raw = paths["raw"] / "nested/retry.png"
    label = paths["labeled"] / "nested/retry.json"
    write(raw)
    write(label, "{}")

    with session_factory() as db:
        scan_candidates(db, settings, "file_name", "data_key", paths["raw"], paths["labeled"])
        candidate = db.scalar(select(SelectionCandidate))
        candidate.selection_status = SelectionStatus.MOVE_FAILED
        stale_copy = paths["selected"] / "dataset/source-data/nested/retry.png"
        stale_copy.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(raw, stale_copy)

        copied = copy_candidate_files(candidate, settings, paths["raw"], paths["labeled"])
        assert len(copied) == 1
        assert raw.is_file()
        assert label.is_file()
        assert stale_copy.is_file()
        assert (paths["selected"] / "dataset/label-data/nested/retry.json").is_file()


def test_path_traversal_is_rejected(roots):
    paths, _, _ = roots
    with pytest.raises(ValueError):
        resolve_safe(paths["raw"], "../outside.txt", must_exist=False)
    with pytest.raises(ValueError):
        resolve_safe(paths["raw"], "/tmp/outside.txt", must_exist=False)
