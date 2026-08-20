from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import logging
import os
from pathlib import Path, PurePosixPath
import queue
import shutil
import threading
from urllib.parse import quote

from PIL import Image, ImageOps

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from .config import Settings
from .models import (
    AppSetting,
    MappingStrategy,
    MatchStatus,
    SelectionCandidate,
    SelectionCandidateFile,
    SelectionStatus,
    utcnow,
)

logger = logging.getLogger(__name__)

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}
THUMBNAIL_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp")
IGNORED_NAMES = {"thumbs.db", ".ds_store"}


@dataclass(frozen=True)
class FileEntry:
    absolute: Path
    relative: str
    name: str
    stem: str
    parent: str
    extension: str
    size: int
    mtime: float

    @property
    def is_image(self) -> bool:
        return self.extension in IMAGE_EXTENSIONS


@dataclass
class MatchResult:
    label: FileEntry
    raw_files: list[FileEntry]
    match_key: str
    status: MatchStatus
    error: str = ""


@dataclass
class CopyOperation:
    source: Path
    destination: Path
    item: SelectionCandidateFile
    backup: Path | None = None


class CopyConflictError(Exception):
    def __init__(self, conflicts: list[str]):
        super().__init__("선별 위치에 같은 경로의 파일이 이미 존재합니다.")
        self.conflicts = conflicts


def get_or_create_settings(db: Session) -> AppSetting:
    row = db.get(AppSetting, 1)
    if row is None:
        row = AppSetting(id=1)
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def discover_files(root: Path, *, label_only: bool = False) -> list[FileEntry]:
    root = root.resolve()
    if not root.exists():
        return []
    entries: list[FileEntry] = []
    for current, directories, filenames in os.walk(root, followlinks=False):
        current_path = Path(current)
        directories[:] = [
            name for name in directories
            if not name.startswith(".") and not (current_path / name).is_symlink()
        ]
        for name in filenames:
            path = current_path / name
            if name.startswith((".", "~")) or name.lower() in IGNORED_NAMES or path.is_symlink():
                continue
            extension = path.suffix.lower()
            if label_only and extension != ".json":
                continue
            try:
                stat = path.stat()
                relative = path.relative_to(root).as_posix()
            except (OSError, ValueError):
                continue
            entries.append(FileEntry(
                absolute=path,
                relative=relative,
                name=name.lower(),
                stem=path.stem.lower(),
                parent=PurePosixPath(relative).parent.as_posix().lower(),
                extension=extension,
                size=stat.st_size,
                mtime=stat.st_mtime,
            ))
    return sorted(entries, key=lambda item: item.relative.lower())


def _group_by_parent(entries: list[FileEntry]) -> dict[str, list[FileEntry]]:
    groups: dict[str, list[FileEntry]] = {}
    for entry in entries:
        groups.setdefault(entry.parent, []).append(entry)
    return groups


def _choose_stem_group(entries: list[FileEntry], preferred_parent: str = "") -> tuple[list[FileEntry], bool]:
    if not entries:
        return [], False
    # 이미지/오브젝트/센서 파일은 보통 서로 다른 하위 폴더에 있지만 같은
    # stem과 서로 다른 확장자를 사용한다. 같은 확장자가 여러 경로에 있으면
    # 어느 파일이 같은 묶음인지 결정할 수 없으므로 충돌로 남긴다.
    by_extension: dict[str, list[FileEntry]] = {}
    for entry in entries:
        by_extension.setdefault(entry.extension, []).append(entry)
    if any(len(group) > 1 for group in by_extension.values()):
        return [], True
    return sorted(entries, key=lambda item: item.relative.lower()), False


def match_by_filename(raw_files: list[FileEntry], labels: list[FileEntry]) -> list[MatchResult]:
    by_stem: dict[str, list[FileEntry]] = {}
    for entry in raw_files:
        by_stem.setdefault(entry.stem, []).append(entry)

    results: list[MatchResult] = []
    for label in labels:
        matched, conflict = _choose_stem_group(by_stem.get(label.stem, []), label.parent)
        if conflict:
            results.append(MatchResult(label, [], label.stem, MatchStatus.CONFLICT, "동일 stem의 원천 폴더가 여러 개입니다."))
        elif not matched:
            results.append(MatchResult(label, [], label.stem, MatchStatus.UNMATCHED, "대응하는 원천 파일을 찾지 못했습니다."))
        else:
            results.append(MatchResult(label, matched, label.stem, MatchStatus.MATCHED))
    return results


def extract_dot_path(document: object, dot_path: str) -> object:
    current = document
    for token in [part for part in dot_path.split(".") if part]:
        if isinstance(current, dict):
            if token not in current:
                raise KeyError(token)
            current = current[token]
        elif isinstance(current, list) and token.isdigit():
            current = current[int(token)]
        else:
            raise KeyError(token)
    return current


def _reference_values(value: object) -> list[str]:
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    if isinstance(value, list) and all(isinstance(item, str) and item.strip() for item in value):
        return list(dict.fromkeys(item.strip() for item in value))
    raise ValueError("JSON 참조키 값은 문자열 또는 문자열 배열이어야 합니다.")


def _resolve_reference(
    reference: str,
    *,
    by_relative: dict[str, list[FileEntry]],
    by_name: dict[str, list[FileEntry]],
    by_stem: dict[str, list[FileEntry]],
) -> tuple[list[FileEntry], bool]:
    normalized = reference.replace("\\", "/").strip().lstrip("./").lower()
    # 경로 참조는 해당 파일 하나를, 파일명 참조는 같은 stem의 복수
    # 원천 파일 묶음을 대표한다.
    if "/" in normalized and normalized and not Path(normalized).is_absolute():
        exact = by_relative.get(normalized, [])
        if len(exact) == 1:
            return exact, False
        if len(exact) > 1:
            return [], True

    file_name = PurePosixPath(normalized).name
    named = by_name.get(file_name, [])
    if len(named) > 1:
        return [], True

    stem = Path(file_name).stem.lower()
    return _choose_stem_group(by_stem.get(stem, []))


def match_by_json_key(raw_files: list[FileEntry], labels: list[FileEntry], json_ref_key: str) -> list[MatchResult]:
    by_relative: dict[str, list[FileEntry]] = {}
    by_name: dict[str, list[FileEntry]] = {}
    by_stem: dict[str, list[FileEntry]] = {}
    for entry in raw_files:
        by_relative.setdefault(entry.relative.lower(), []).append(entry)
        by_name.setdefault(entry.name, []).append(entry)
        by_stem.setdefault(entry.stem, []).append(entry)

    results: list[MatchResult] = []
    for label in labels:
        try:
            with label.absolute.open("r", encoding="utf-8-sig") as stream:
                document = json.load(stream)
            references = _reference_values(extract_dot_path(document, json_ref_key))
        except Exception as exc:
            results.append(MatchResult(label, [], json_ref_key, MatchStatus.ERROR, f"JSON 참조키 처리 실패: {exc}"))
            continue

        resolved: list[FileEntry] = []
        seen: set[str] = set()
        missing: list[str] = []
        conflicts: list[str] = []
        for reference in references:
            matched, conflict = _resolve_reference(
                reference, by_relative=by_relative, by_name=by_name, by_stem=by_stem
            )
            if conflict:
                conflicts.append(reference)
                continue
            if not matched:
                missing.append(reference)
                continue
            for entry in matched:
                if entry.relative not in seen:
                    seen.add(entry.relative)
                    resolved.append(entry)

        key = " | ".join(references)
        if conflicts:
            results.append(MatchResult(label, resolved, key, MatchStatus.CONFLICT, f"복수 원천 경로와 충돌: {', '.join(conflicts)}"))
        elif missing:
            results.append(MatchResult(label, resolved, key, MatchStatus.UNMATCHED, f"원천 파일 누락: {', '.join(missing)}"))
        else:
            results.append(MatchResult(label, resolved, key, MatchStatus.MATCHED))
    return results


def _fingerprint(result: MatchResult) -> str:
    parts = [
        f"{entry.relative}|{entry.size}|{entry.mtime:.6f}"
        for entry in sorted(result.raw_files, key=lambda item: item.relative.lower())
    ]
    parts.extend([
        f"{result.label.relative}|{result.label.size}|{result.label.mtime:.6f}",
        result.status,
        result.match_key,
    ])
    return sha256("\n".join(parts).encode("utf-8")).hexdigest()


def _scan_key(strategy: str, label_relative_path: str) -> str:
    return sha256(f"{strategy}\n{label_relative_path.lower()}".encode("utf-8")).hexdigest()


def resolve_directory(root: Path, relative_path: str) -> Path:
    target = resolve_safe(root, relative_path, must_exist=False)
    if not target.is_dir() or target.is_symlink():
        raise ValueError(f"데이터 폴더를 찾을 수 없습니다: {relative_path}")
    return target


def configured_data_roots(settings: Settings, app_setting: AppSetting) -> tuple[Path, Path]:
    if not app_setting.paths_configured or not app_setting.raw_relative_path or not app_setting.labeled_relative_path:
        raise ValueError("데이터 루트에서 원천데이터 폴더와 라벨데이터 폴더를 각각 선택하세요.")
    raw_root = resolve_directory(settings.data_root_path, app_setting.raw_relative_path)
    labeled_root = resolve_directory(settings.data_root_path, app_setting.labeled_relative_path)
    if raw_root == labeled_root:
        raise ValueError("원천데이터와 라벨데이터 폴더는 서로 달라야 합니다.")
    return raw_root, labeled_root


def scan_candidates(
    db: Session, settings: Settings, strategy: str, json_ref_key: str,
    raw_root: Path | None = None, labeled_root: Path | None = None,
) -> dict[str, int]:
    if raw_root is None or labeled_root is None:
        raw_root, labeled_root = configured_data_roots(settings, get_or_create_settings(db))
    raw_files = discover_files(raw_root)
    labels = discover_files(labeled_root, label_only=True)
    if strategy == MappingStrategy.JSON_REF_KEY:
        matched_results = match_by_json_key(raw_files, labels, json_ref_key)
    else:
        matched_results = match_by_filename(raw_files, labels)

    counters = {"created": 0, "updated": 0, "skipped_selected": 0, **{status.value: 0 for status in MatchStatus}}
    for result in matched_results:
        counters[result.status.value] += 1
        scan_key = _scan_key(strategy, result.label.relative)
        fingerprint = _fingerprint(result)
        candidate = db.scalar(
            select(SelectionCandidate)
            .options(selectinload(SelectionCandidate.files))
            .where(SelectionCandidate.scan_key == scan_key)
        )
        if candidate is None:
            candidate = db.scalar(
                select(SelectionCandidate)
                .options(selectinload(SelectionCandidate.files))
                .where(SelectionCandidate.fingerprint == fingerprint)
            )
        if candidate and candidate.selection_status == SelectionStatus.SELECTED:
            counters["skipped_selected"] += 1
            continue
        if candidate is None:
            candidate = SelectionCandidate(
                scan_key=scan_key,
                fingerprint=fingerprint,
                mapping_strategy=strategy,
                match_key=result.match_key,
                match_status=result.status,
                error_message=result.error,
            )
            db.add(candidate)
            counters["created"] += 1
        else:
            candidate.files.clear()
            candidate.scan_key = scan_key
            candidate.fingerprint = fingerprint
            candidate.mapping_strategy = strategy
            candidate.match_key = result.match_key
            candidate.match_status = result.status
            candidate.error_message = result.error
            if candidate.selection_status == SelectionStatus.MOVE_FAILED:
                candidate.selection_status = SelectionStatus.PENDING
            counters["updated"] += 1

        for order, entry in enumerate(result.raw_files):
            candidate.files.append(SelectionCandidateFile(
                file_group="raw", reference_order=order,
                original_relative_path=entry.relative, extension=entry.extension,
                size=entry.size, mtime=entry.mtime, is_previewable_image=entry.is_image,
            ))
        candidate.files.append(SelectionCandidateFile(
            file_group="labeled", reference_order=len(result.raw_files),
            original_relative_path=result.label.relative, extension=result.label.extension,
            size=result.label.size, mtime=result.label.mtime, is_previewable_image=False,
        ))
    db.commit()
    return {
        "scanned_raw_files": len(raw_files),
        "scanned_label_files": len(labels),
        **counters,
    }


def resolve_safe(root: Path, relative_path: str, *, must_exist: bool = True) -> Path:
    relative = Path(relative_path)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("허용되지 않는 파일 경로입니다.")
    root_resolved = root.resolve()
    target = (root_resolved / relative).resolve(strict=False)
    if not target.is_relative_to(root_resolved):
        raise ValueError("데이터 루트 밖의 경로에는 접근할 수 없습니다.")
    if must_exist and not target.is_file():
        raise FileNotFoundError(relative_path)
    if must_exist and target.is_symlink():
        raise ValueError("심볼릭 링크 파일에는 접근할 수 없습니다.")
    return target


def candidate_query():
    return select(SelectionCandidate).options(selectinload(SelectionCandidate.files))


def file_url(file: SelectionCandidateFile) -> str:
    if file.selected_relative_path:
        group, path = "selected", file.selected_relative_path
    else:
        group, path = file.file_group, file.original_relative_path
    return f"/api/files/{group}?path={quote(path, safe='')}"


_thumbnail_jobs: dict[str, str] = {}
_thumbnail_jobs_lock = threading.Lock()
_thumbnail_queue: queue.Queue[tuple[Settings, Path, str, Path]] = queue.Queue()
_thumbnail_worker_start_lock = threading.Lock()
_thumbnail_worker_started = False


def thumbnail_job_status(raw_relative_path: str) -> str | None:
    with _thumbnail_jobs_lock:
        return _thumbnail_jobs.get(raw_relative_path)


def thumbnail_data_relative_path(settings: Settings, raw_root: Path, raw_relative_path: str) -> str:
    data_relative_root = raw_root.resolve().relative_to(settings.data_root_path.resolve())
    return (data_relative_root / Path(raw_relative_path)).as_posix()


def thumbnail_cache_path(settings: Settings, raw_root: Path, raw_relative_path: str) -> Path:
    if not settings.thumbnail_root_path:
        raise ValueError("THUMBNAIL_ROOT_PATH가 설정되지 않았습니다.")
    cache_root = settings.thumbnail_root_path
    relative = thumbnail_data_relative_path(settings, raw_root, raw_relative_path)
    return resolve_safe(cache_root, relative, must_exist=False).with_suffix(".jpg")


def find_thumbnail(settings: Settings, thumbnail_relative_path: str, raw_root: Path, raw_relative_path: str) -> Path | None:
    if not settings.thumbnail_enabled:
        return None
    thumbnail_root = settings.thumbnail_root_path / thumbnail_relative_path if thumbnail_relative_path else settings.thumbnail_root_path
    relative = Path(thumbnail_data_relative_path(settings, raw_root, raw_relative_path))
    safe_target = resolve_safe(thumbnail_root, relative.as_posix(), must_exist=False)
    directory = safe_target.parent
    for suffix in (relative.suffix.lower(), *THUMBNAIL_EXTENSIONS):
        candidate = directory / f"{relative.stem}{suffix}"
        if candidate.is_file() and not candidate.is_symlink():
            return candidate
    cached = thumbnail_cache_path(settings, raw_root, raw_relative_path)
    return cached if cached.is_file() else None


def thumbnail_state(settings: Settings, thumbnail_relative_path: str, raw_root: Path, raw_relative_path: str, raw_path: Path | None = None) -> tuple[str, Path | None]:
    if not settings.thumbnail_enabled:
        return "unavailable", None
    found = find_thumbnail(settings, thumbnail_relative_path, raw_root, raw_relative_path)
    if found:
        return "available", found
    with _thumbnail_jobs_lock:
        if _thumbnail_jobs.get(raw_relative_path) in {"pending", "generating"}:
            return "generating", None
    if raw_path is not None and raw_path.suffix.lower() in IMAGE_EXTENSIONS:
        return "missing", None
    return "unavailable", None


def generate_thumbnail(settings: Settings, raw_root: Path, raw_relative_path: str, raw_path: Path) -> None:
    cache_path = thumbnail_cache_path(settings, raw_root, raw_relative_path)
    logger.debug("thumbnail generation started: source=%s cache=%s", raw_path, cache_path)
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        with Image.open(raw_path) as image:
            image = ImageOps.exif_transpose(image).convert("RGB")
            image.thumbnail((360, 360), Image.Resampling.LANCZOS)
            image.save(cache_path, "JPEG", quality=86, optimize=True)
        with _thumbnail_jobs_lock:
            _thumbnail_jobs[raw_relative_path] = "available"
        logger.info("thumbnail generation completed: source=%s cache=%s", raw_path, cache_path)
    except Exception as exc:
        with _thumbnail_jobs_lock:
            _thumbnail_jobs[raw_relative_path] = "unavailable"
        logger.exception("thumbnail generation failed: source=%s cache=%s error=%s", raw_path, cache_path, exc)


def _thumbnail_worker() -> None:
    while True:
        settings, raw_root, relative, raw_path = _thumbnail_queue.get()
        try:
            with _thumbnail_jobs_lock:
                _thumbnail_jobs[relative] = "generating"
            generate_thumbnail(settings, raw_root, relative, raw_path)
        except Exception:
            with _thumbnail_jobs_lock:
                _thumbnail_jobs[relative] = "unavailable"
            logger.exception("thumbnail worker failed: source=%s", raw_path)
        finally:
            _thumbnail_queue.task_done()


def _ensure_thumbnail_worker() -> None:
    global _thumbnail_worker_started
    if _thumbnail_worker_started:
        return
    with _thumbnail_worker_start_lock:
        if _thumbnail_worker_started:
            return
        threading.Thread(target=_thumbnail_worker, name="thumbnail-worker", daemon=True).start()
        _thumbnail_worker_started = True


def queue_thumbnail_generation(settings: Settings, thumbnail_relative_path: str, raw_root: Path, files: list[str]) -> int:
    _ensure_thumbnail_worker()
    queued = 0
    for relative in files:
        raw_path = resolve_safe(raw_root, relative)
        state, _ = thumbnail_state(settings, thumbnail_relative_path, raw_root, relative, raw_path)
        if state != "missing":
            continue
        with _thumbnail_jobs_lock:
            if _thumbnail_jobs.get(relative) in {"pending", "generating"}:
                continue
            _thumbnail_jobs[relative] = "pending"
        _thumbnail_queue.put((settings, raw_root, relative, raw_path))
        queued += 1
    return queued


def read_label_json(candidate: SelectionCandidate, settings: Settings, labeled_root: Path) -> object | None:
    label = next((item for item in candidate.files if item.file_group == "labeled"), None)
    if not label:
        return None
    root = settings.selected_data_path if label.selected_relative_path else labeled_root
    relative = label.selected_relative_path or label.original_relative_path
    try:
        path = resolve_safe(root, relative)
        if path.stat().st_size > 20 * 1024 * 1024:
            return {"_error": "라벨 JSON이 20MB를 초과하여 원문을 표시하지 않습니다."}
        with path.open("r", encoding="utf-8-sig") as stream:
            return json.load(stream)
    except Exception as exc:
        return {"_error": f"라벨 JSON 로딩 실패: {exc}"}


def _matches_existing_copy(source: Path, destination: Path) -> bool:
    try:
        source_stat, destination_stat = source.stat(), destination.stat()
        return (
            destination.is_file()
            and source_stat.st_size == destination_stat.st_size
            and abs(source_stat.st_mtime - destination_stat.st_mtime) < 1
        )
    except OSError:
        return False


def copy_candidate_files(
    candidate: SelectionCandidate, settings: Settings, raw_root: Path, labeled_root: Path, *, overwrite: bool = False,
) -> list[CopyOperation]:
    if candidate.match_status != MatchStatus.MATCHED:
        raise ValueError("정상 매칭된 후보만 선택할 수 있습니다.")
    if candidate.selection_status == SelectionStatus.SELECTED:
        return []

    planned: list[tuple[Path, Path, SelectionCandidateFile, bool]] = []
    for item in candidate.files:
        source_root = raw_root if item.file_group == "raw" else labeled_root
        source = resolve_safe(source_root, item.original_relative_path)
        try:
            data_root_relative = source.relative_to(settings.data_root_path.resolve())
        except ValueError as exc:
            raise ValueError("원천 또는 라벨 파일이 DATA_ROOT_PATH 밖에 있습니다.") from exc
        selected_relative = data_root_relative.as_posix()
        destination = resolve_safe(settings.selected_data_path, selected_relative, must_exist=False)
        reuse_failed_copy = (
            destination.exists()
            and candidate.selection_status == SelectionStatus.MOVE_FAILED
            and _matches_existing_copy(source, destination)
        )
        if destination.exists() and not reuse_failed_copy and not overwrite:
            planned.append((source, destination, item, False))
            continue
        planned.append((source, destination, item, reuse_failed_copy))

    conflicts = [
        destination.relative_to(settings.selected_data_path.resolve()).as_posix()
        for _, destination, _, already_copied in planned
        if destination.exists() and not already_copied and not overwrite
    ]
    if conflicts:
        raise CopyConflictError(conflicts)

    copied: list[CopyOperation] = []
    try:
        for source, destination, item, already_copied in planned:
            destination.parent.mkdir(parents=True, exist_ok=True)
            if not already_copied:
                backup = None
                if destination.exists():
                    backup = destination.with_name(f".{destination.name}.prework-{candidate.id}.bak")
                    if backup.exists():
                        raise FileExistsError(f"덮어쓰기 백업 파일이 이미 존재합니다: {backup.name}")
                    destination.replace(backup)
                operation = CopyOperation(source, destination, item, backup)
                copied.append(operation)
                # NTFS 등 외부 볼륨의 macOS 파일 플래그를 APFS 대상에
                # 적용하는 copy2()는 chflags 단계에서 EPERM이 발생할 수
                # 있으므로 파일 내용만 복사한다.
                shutil.copyfile(source, destination)
                try:
                    source_stat = source.stat()
                    os.utime(destination, ns=(source_stat.st_atime_ns, source_stat.st_mtime_ns))
                except OSError as metadata_error:
                    logger.warning("파일 메타데이터 적용을 건너뜁니다: source=%s destination=%s error=%s", source, destination, metadata_error)
            item.selected_relative_path = destination.relative_to(settings.selected_data_path.resolve()).as_posix()
    except Exception:
        rollback_copies(copied)
        for _, _, item, _ in planned:
            item.selected_relative_path = ""
        raise
    return copied


def rollback_copies(copied: list[CopyOperation]) -> None:
    for operation in reversed(copied):
        try:
            if operation.destination.is_file():
                operation.destination.unlink()
            if operation.backup and operation.backup.is_file():
                operation.backup.replace(operation.destination)
        except OSError:
            pass


def finalize_copies(copied: list[CopyOperation]) -> None:
    for operation in copied:
        try:
            if operation.backup and operation.backup.is_file():
                operation.backup.unlink()
        except OSError:
            pass


def selection_summary(db: Session) -> dict[str, int]:
    rows = db.execute(
        select(SelectionCandidate.selection_status, func.count())
        .group_by(SelectionCandidate.selection_status)
    ).all()
    summary = {status.value: 0 for status in SelectionStatus}
    summary.update({str(status): int(count) for status, count in rows})
    summary["total"] = sum(summary[status.value] for status in SelectionStatus)
    return summary
