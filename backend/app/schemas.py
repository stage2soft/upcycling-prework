from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

class SettingsPayload(BaseModel):
    mapping_strategy: Literal["file_name", "json_ref_key"] = "file_name"
    json_ref_key: str = Field(default="data_key", max_length=300)
    raw_relative_path: str = Field(default="", max_length=1000)
    labeled_relative_path: str = Field(default="", max_length=1000)
    annotation_method_code: Literal["bbox_2d", "bbox_3d", "polygon", "segmentation"] = "bbox_2d"

    @field_validator("json_ref_key")
    @classmethod
    def validate_key(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("JSON 참조키를 입력하세요.")
        return value

    @field_validator("raw_relative_path", "labeled_relative_path")
    @classmethod
    def validate_relative_path(cls, value: str) -> str:
        value = value.strip().replace("\\", "/").strip("/")
        if not value or value == "." or ".." in value.split("/"):
            raise ValueError("데이터 루트 이하의 폴더를 선택하세요.")
        return value


class ScanRequest(BaseModel):
    mapping_strategy: Literal["file_name", "json_ref_key"] | None = None
    json_ref_key: str | None = None
    raw_relative_path: str | None = None
    labeled_relative_path: str | None = None
    annotation_method_code: Literal["bbox_2d", "bbox_3d", "polygon", "segmentation"] | None = None


class DecisionRequest(BaseModel):
    decision: Literal["selected", "rejected"]
    overwrite: bool = False


class CandidateFileResponse(BaseModel):
    id: int
    file_group: str
    reference_order: int
    original_relative_path: str
    selected_relative_path: str
    extension: str
    size: int
    mtime: float
    is_previewable_image: bool
    file_url: str


class CandidateResponse(BaseModel):
    id: str
    fingerprint: str
    match_key: str
    mapping_strategy: str
    match_status: str
    selection_status: str
    error_message: str
    created_at: datetime
    updated_at: datetime
    decided_at: datetime | None
    files: list[CandidateFileResponse]
    label_json: object | None = None


class ScanResponse(BaseModel):
    scanned_raw_files: int
    scanned_label_files: int
    created: int
    updated: int
    skipped_selected: int
    matched: int
    unmatched: int
    conflict: int
    error: int


class PageResponse(BaseModel):
    results: list[CandidateResponse]
    count: int
    page: int
    page_size: int
    total_pages: int
    summary: dict[str, int]
