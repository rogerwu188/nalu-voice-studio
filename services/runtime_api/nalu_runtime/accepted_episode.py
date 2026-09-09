"""Prepare a complete ordered video input set; audio/captions/QA remain separate."""

import os
import tempfile
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .models import PostproductionShotSource
from .repair_video_adoption import read_repair_clip
from .repository import ConflictError, encode, new_id, utc_now
from .secure_files import secure_directory, sync_directory
from .shot_planning import ShotPlan, ShotPlanningService
from .shot_review import ShotReviewService
from .video_materialization import VideoMaterializationService
from .video_preparation import digest
from .video_tail import VideoTailService


class EpisodeCut(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    shot_index: int = Field(strict=True, ge=0, le=119)
    source_in_seconds: float = Field(ge=0)
    source_out_seconds: float = Field(gt=0)

    @model_validator(mode="after")
    def positive_window(self):
        if self.source_out_seconds <= self.source_in_seconds:
            raise ValueError("cut must have positive duration")
        return self


class EpisodeEditRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_input_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    cuts: list[EpisodeCut] = Field(min_length=1, max_length=120)


class AcceptedEpisodeService:
    def __init__(self, repository, data_root):
        self.repository, self.data_root = repository, Path(data_root).resolve()

    def stage(self, run_id, selection: EpisodeEditRequest | None = None):
        repo = self.repository
        with repo.db.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            run = repo.get_run(run_id)
            if repo.get_project(run.project_id).archived_at:
                raise ConflictError("archived project is read-only")
            package = ShotPlanningService(repo)._package(run)
            plan = ShotReviewService(repo).current(run_id)
            if (plan is None or plan.event_type != "shot_plan_approved" or plan.payload.get("approved") is not True
                    or plan.payload.get("plan_sha256") != digest({k: v for k, v in plan.payload.items() if k != "plan_sha256"})
                    or plan.payload.get("production_package_sha256") != package["package_sha256"]):
                raise ConflictError("confirm the current episode shot plan before postproduction")
            shots = ShotPlan.model_validate(plan.payload["plan"]).shots
            tasks = plan.payload.get("tasks", [])
            if len(tasks) != len(shots) or sum(s.duration_seconds for s in shots) != repo.get_episode(run.episode_id).target_seconds:
                raise ConflictError("episode duration or shot inventory changed")
            events = repo.list_run_events(run_id)
            items = []
            for index, shot in enumerate(shots):
                matching = [t for t in tasks if t.get("shot_index") == index]
                if len(matching) != 1:
                    raise ConflictError("episode shot ordering is ambiguous")
                task = matching[0]["task_key"]
                reviews = [e for e in events if e.event_type == "video_shot_reviewed" and e.payload.get("task_key") == task]
                reused = [e for e in events if e.event_type == "repair_video_reviewed"
                          and e.payload.get("shot_index") == index]
                reuse = reused[-1] if not reviews and reused else None
                if not reviews and reuse is None:
                    raise ConflictError(f"shot {index + 1} has no adopted video")
                if reuse is not None:
                    review, media, _ = read_repair_clip(repo, self.data_root, run_id, reuse.id)
                else:
                    review, media, _ = VideoTailService(repo, self.data_root).accepted_video(run_id, reviews[-1].id)
                if reuse is None and (review.payload.get("approved_plan_event_id") != plan.id
                        or review.payload.get("approved_plan_sha256") != plan.payload["plan_sha256"]):
                    raise ConflictError("adopted video belongs to another plan")
                item = {"shot_index": index, "task_key": task, "review_id": review.id,
                        "review_sha256": review.payload["review_sha256"], "materialization_id": media.id,
                        "video_sha256": media.payload["video"]["sha256"], "duration_seconds": shot.duration_seconds,
                        "source_duration_seconds": media.payload["video"]["duration_seconds"],
                        "provider_task_id": repo.get_remote_task_binding(media.payload["binding_id"]).provider_task_id}
                items.append(item)
                if reuse is not None:
                    item.update(repair_review_id=reuse.id, source_run_id=review.run_id)
            if sum(item["duration_seconds"] for item in items) > 1800:
                raise ConflictError("episode exceeds the postproduction duration limit")
            if len({item["task_key"] for item in items}) != len(items):
                raise ConflictError("episode has duplicate shot identities")
            identity = digest({"plan_id": plan.id, "plan_sha256": plan.payload["plan_sha256"], "items": items})
            package_path = Path(run.package_path).absolute()
            runs = self.data_root / "runs"
            if not package_path.is_relative_to(runs) or package_path.resolve() != package_path:
                raise ConflictError("episode package is outside managed run storage")
            directory = package_path.parent / "qingshan-workspace" / "exports" / "provider-results" / "accepted-shots" / identity
            # Validate every managed component before creating descendants.
            current = self.data_root
            for part in directory.relative_to(self.data_root).parts:
                current = current / part
                if current.is_symlink() or (current.exists() and not current.is_dir()):
                    raise ConflictError("postproduction input storage cannot be a symlink")
                secure_directory(current)
            sources = []
            for item in items:
                if item.get("repair_review_id"):
                    _, _, raw = read_repair_clip(repo, self.data_root, run_id, item["repair_review_id"])
                else:
                    _, raw = VideoMaterializationService(repo, self.data_root).read_saved(run_id, item["materialization_id"])
                filename = f"shot-{item['shot_index'] + 1:03d}-{item['video_sha256']}.mp4"
                destination = directory / filename
                if destination.exists() or destination.is_symlink():
                    if destination.is_symlink() or not destination.is_file() or destination.stat().st_size != len(raw) or destination.read_bytes() != raw:
                        raise ConflictError("staged episode video changed; reconcile before rendering")
                else:
                    fd, name = tempfile.mkstemp(prefix=".video-", dir=directory)
                    try:
                        with os.fdopen(fd, "wb") as output:
                            output.write(raw); output.flush(); os.fsync(output.fileno())
                        os.link(name, destination)
                    finally:
                        Path(name).unlink(missing_ok=True)
                    sync_directory(directory)
                sources.append(PostproductionShotSource(shot_id=item["task_key"],
                    source_relative_path=f"provider-results/accepted-shots/{identity}/{filename}", source_sha256=item["video_sha256"],
                    source_task_id=item["provider_task_id"], source_receipt_sha256=item["review_sha256"],
                    source_in_seconds=0, source_out_seconds=item["duration_seconds"]).model_dump())
            record = {"run_id": run_id, "episode_id": run.episode_id, "plan_id": plan.id,
                      "plan_sha256": plan.payload["plan_sha256"], "production_package_sha256": package["package_sha256"],
                      "items": items, "shots": sources, "generation_performed": False, "master_accepted": False,
                      "audio_complete": False, "captions_complete": False, "professional_qa_complete": False}
            record["editorial_selection_complete"] = False
            record["source_windows_are_unedited"] = True
            record["input_sha256"] = digest(record)
            event_type = "postproduction_shot_inputs_staged"
            if selection is not None:
                if selection.expected_input_sha256 != record["input_sha256"]:
                    raise ConflictError("adopted episode inputs changed before editing")
                if [cut.shot_index for cut in selection.cuts] != list(range(len(items))):
                    raise ConflictError("edit must cover every shot once in confirmed order")
                edited, timeline, cursor = [], [], 0
                for cut, source, item in zip(selection.cuts, sources, items, strict=True):
                    if cut.source_out_seconds > item["source_duration_seconds"]:
                        raise ConflictError("edit exceeds the adopted source video")
                    # Match the downstream lineage QA's 50 ms whole-source guard.
                    if cut.source_in_seconds <= 0.05 and cut.source_out_seconds >= item["source_duration_seconds"] - 0.05:
                        raise ConflictError("choose an editorial window; whole-provider passthrough is forbidden")
                    frames = round((cut.source_out_seconds - cut.source_in_seconds) * 24)
                    if frames < 1:
                        raise ConflictError("edit is shorter than one output frame")
                    duration = frames / 24
                    if cut.source_in_seconds + duration > item["source_duration_seconds"]:
                        raise ConflictError("frame-rounded edit exceeds the source")
                    edited.append(PostproductionShotSource.model_validate({**source,
                        "source_in_seconds": cut.source_in_seconds, "source_out_seconds": cut.source_out_seconds}).model_dump())
                    timeline.append({"shot_index": cut.shot_index, "start_seconds": cursor,
                                     "duration_seconds": duration, "frame_count": frames})
                    cursor += duration
                source_input_sha256 = record.pop("input_sha256")
                record = {**record, "shots": edited, "source_input_sha256": source_input_sha256,
                          "timeline": timeline, "frame_rate": 24, "edited_duration_seconds": cursor,
                          "planned_duration_seconds": sum(item["duration_seconds"] for item in items),
                          "source_windows_are_unedited": False, "editorial_selection_complete": True,
                          "edit_approved": False, "captions_require_retiming": True}
                record["edit_sha256"] = digest(record)
                event_type = "postproduction_edit_drafted"
            for event in events:
                if event.event_type == event_type and event.payload == record:
                    return event
            event_id = new_id("evt")
            sequence = db.execute("SELECT COALESCE(MAX(sequence),0)+1 FROM run_events WHERE run_id=?", (run_id,)).fetchone()[0]
            db.execute("INSERT INTO run_events VALUES (?,?,?,?,?,?,?,?,?)", (event_id, run_id, sequence,
                event_type, None, None, "Episode video inputs prepared; edit approval, audio, captions and QA remain required.", encode(record), utc_now()))
        return repo.get_run_event(event_id)
