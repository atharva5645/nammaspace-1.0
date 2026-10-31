from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class OpeningInput(BaseModel):
    id: str = Field(min_length=1, max_length=80)
    label: str = Field(min_length=1, max_length=120)
    kind: Literal["door", "window", "other"]
    side: Literal["side1", "side2", "side3", "side4"]
    width: float | None = Field(default=None, gt=0, le=100)
    height: float | None = Field(default=None, gt=0, le=100)
    offset_from_corner: float | None = Field(default=None, ge=0, le=1000)

    @field_validator("label")
    @classmethod
    def trim_label(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("An opening label is required")
        return cleaned


class AnchorPixelPick(BaseModel):
    image_filename: str = Field(min_length=1, max_length=255)
    x_normalized: float = Field(ge=0, le=1)
    y_normalized: float = Field(ge=0, le=1)


class ProjectCreate(BaseModel):
    project_name: str = Field(min_length=2, max_length=120)
    room_name: str = Field(default="Room 1", min_length=1, max_length=120)
    units: Literal["m", "ft"] = "m"
    known_distance: float = Field(gt=0, le=1000)
    anchor_name: str = Field(default="Measured span", min_length=2, max_length=120)
    anchor_start_label: str = Field(default="Endpoint A", min_length=2, max_length=120)
    anchor_end_label: str = Field(default="Endpoint B", min_length=2, max_length=120)
    anchor_view_side: Literal["side1", "side2", "side3", "side4"] = "side1"
    anchor_source: Literal["tape", "laser", "floor_plan", "sensor"] = "tape"
    anchor_confidence: Literal["high", "medium", "low"] = "medium"
    anchor_start_pick: AnchorPixelPick | None = None
    anchor_end_pick: AnchorPixelPick | None = None
    room_length: float | None = Field(default=None, gt=0, le=1000)
    room_width: float | None = Field(default=None, gt=0, le=1000)
    openings: list[OpeningInput] = Field(default_factory=list, max_length=50)
    ceiling_height: float | None = Field(default=None, gt=0, le=100)
    sop_version: Literal["capture-v1"] = "capture-v1"
    sop_acknowledgments: list[Literal["overlap", "corners_openings", "steady_lighting"]] = Field(min_length=3, max_length=3)

    @field_validator("project_name", "room_name", "anchor_name", "anchor_start_label", "anchor_end_label")
    @classmethod
    def trim_names(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("A non-empty name is required")
        return cleaned

    @field_validator("sop_acknowledgments")
    @classmethod
    def require_all_sop_acknowledgments(cls, value: list[str]) -> list[str]:
        if set(value) != {"overlap", "corners_openings", "steady_lighting"}:
            raise ValueError("All capture SOP acknowledgments are required")
        return value

    @model_validator(mode="after")
    def require_paired_anchor_picks(self):
        if bool(self.anchor_start_pick) != bool(self.anchor_end_pick):
            raise ValueError("Mark both measurement endpoints in the same photo, or leave both unmarked")
        if self.anchor_start_pick and self.anchor_end_pick and self.anchor_start_pick.image_filename != self.anchor_end_pick.image_filename:
            raise ValueError("Both measurement endpoints must refer to the same photo")
        return self


class WireframeRevisionInput(BaseModel):
    length: float = Field(gt=0, le=1000)
    width: float = Field(gt=0, le=1000)
    height: float = Field(gt=0, le=100)
    openings: list[OpeningInput] = Field(default_factory=list, max_length=50)


class UploadCreate(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    content_type: str = Field(min_length=3, max_length=120)
    byte_size: int = Field(gt=0, le=536870912)
    sha256: str | None = Field(default=None, pattern=r"^[a-fA-F0-9]{64}$")
    category: Literal["room_image", "extra_image", "video", "floor_plan", "sensor_data"]
    side: Literal["side1", "side2", "side3", "side4"] | None = None

    @field_validator("filename")
    @classmethod
    def require_filename(cls, value: str) -> str:
        cleaned = value.replace("\\", "/").split("/")[-1].strip()
        if not cleaned or cleaned in {".", ".."}:
            raise ValueError("A valid filename is required")
        return cleaned

    @model_validator(mode="after")
    def side_matches_category(self):
        if self.category == "room_image" and self.side is None:
            raise ValueError("Each required room image must be assigned to a side")
        if self.category != "room_image" and self.side is not None:
            raise ValueError("Only required room images use a side assignment")
        return self


class UploadCreated(BaseModel):
    upload_id: str
    chunk_size: int
    expected_parts: int
    uploaded_parts: list[int]
    status: str


class ProjectResponse(BaseModel):
    project_id: str
    project_name: str
    room_name: str
    units: str
    known_distance: float
    anchor_name: str = "Measured span"
    anchor_start_label: str = "Endpoint A"
    anchor_end_label: str = "Endpoint B"
    anchor_view_side: str = "side1"
    anchor_source: str = "tape"
    anchor_confidence: str = "medium"
    anchor_start_pick: AnchorPixelPick | None = None
    anchor_end_pick: AnchorPixelPick | None = None
    room_length: float | None = None
    room_width: float | None = None
    openings: list[OpeningInput] = Field(default_factory=list)
    ceiling_height: float | None
    created_at: str


class ProjectUploadSummary(BaseModel):
    filename: str
    category: Literal["room_image", "extra_image", "video", "floor_plan", "sensor_data"]
    side: Literal["side1", "side2", "side3", "side4"] | None
    byte_size: int
    status: Literal["receiving", "complete", "rejected"]


class JobResponse(BaseModel):
    job_id: str
    project_id: str
    kind: str
    contract_version: str = "spatial-job.v1"
    status: str
    report: dict | None = None
    result: dict | None = None
    error_code: str | None = None
    created_at: str
    updated_at: str


class ProjectWorkspaceResponse(ProjectResponse):
    sop_version: str
    sop_acknowledgments: list[str]
    uploads: list[ProjectUploadSummary]
    latest_job: JobResponse | None = None


class ProjectListItem(BaseModel):
    project_id: str
    project_name: str
    room_name: str
    units: str
    created_at: str
    image_count: int
    evidence_count: int
    latest_job_status: str | None = None
