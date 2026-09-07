"""Prepare a complete ordered video input set; audio/captions/QA remain separate."""

import os
import tempfile
from pathlib import Path

from .models import PostproductionShotSource
from .repository import ConflictError, encode, new_id, utc_now
from .secure_files import secure_directory, sync_directory
from .shot_planning import ShotPlan, ShotPlanningService
from .shot_review import ShotReviewService
from .video_materialization import VideoMaterializationService
from .video_preparation import digest
from .video_tail import VideoTailService


class AcceptedEpisodeService:
    def __init__(self, repository, data_root):
        self.repository, self.data_root = repository, Path(data_root).resolve()

    def stage(self, run_id):
        repo = self.repository
        with repo.db.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            run = repo.get_run(run_id)
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
                if not reviews:
                    raise ConflictError(f"shot {index + 1} has no adopted video")
                review, media, _ = VideoTailService(repo, self.data_root).accepted_video(run_id, reviews[-1].id)
                if (review.payload.get("approved_plan_event_id") != plan.id
                        or review.payload.get("approved_plan_sha256") != plan.payload["plan_sha256"]):
                    raise ConflictError("adopted video belongs to another plan")
                item = {"shot_index": index, "task_key": task, "review_id": review.id,
                        "review_sha256": review.payload["review_sha256"], "materialization_id": media.id,
                        "video_sha256": media.payload["video"]["sha256"], "duration_seconds": shot.duration_seconds,
                        "provider_task_id": repo.get_remote_task_binding(media.payload["binding_id"]).provider_task_id}
                items.append(item)
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
            for event in events:
                if event.event_type == "postproduction_shot_inputs_staged" and event.payload == record:
                    return event
            event_id = new_id("evt")
            sequence = db.execute("SELECT COALESCE(MAX(sequence),0)+1 FROM run_events WHERE run_id=?", (run_id,)).fetchone()[0]
            db.execute("INSERT INTO run_events VALUES (?,?,?,?,?,?,?,?,?)", (event_id, run_id, sequence,
                "postproduction_shot_inputs_staged", None, None, "Adopted episode videos staged; audio, captions and QA remain required.", encode(record), utc_now()))
        return repo.get_run_event(event_id)
