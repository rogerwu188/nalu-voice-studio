"""Draft timed captions and sound needs from confirmed shots, never fabricate audio."""

import html

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .repository import ConflictError, encode, new_id, utc_now
from .shot_planning import ShotPlan, ShotPlanningService
from .shot_review import ShotReviewService
from .video_preparation import digest


class EpisodeSoundPlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_plan_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    edit_id: str | None = Field(default=None, min_length=1, max_length=160)
    expected_edit_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def paired_edit(self):
        if (self.edit_id is None) != (self.expected_edit_sha256 is None):
            raise ValueError("edited timing requires both the edit ID and its hash")
        return self


def srt_time(seconds):
    milliseconds = round(seconds * 1000)
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, milliseconds = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"


class EpisodeSoundPlanService:
    def __init__(self, repository, data_root=None):
        self.repository = repository
        self.data_root = data_root

    def prepare(self, run_id, expected_plan_sha256, *, edit_id=None, expected_edit_sha256=None):
        repo = self.repository
        with repo.db.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            run = repo.get_run(run_id)
            if repo.get_project(run.project_id).archived_at:
                raise ConflictError("archived project is read-only")
            package = ShotPlanningService(repo)._package(run)
            event = ShotReviewService(repo).current(run_id)
            if (event is None or event.event_type != "shot_plan_approved" or event.payload.get("approved") is not True
                    or event.payload.get("plan_sha256") != expected_plan_sha256
                    or digest({k: v for k, v in event.payload.items() if k != "plan_sha256"}) != expected_plan_sha256
                    or event.payload.get("production_package_sha256") != package["package_sha256"]):
                raise ConflictError("sound planning requires the current confirmed shot plan")
            episode = repo.get_episode(run.episode_id)
            script = package["approved_script"]
            saved_script = repo.get_script(episode.id, script["revision"])
            if (episode.approved_script_revision != script["revision"]
                    or event.payload.get("script_revision") != script["revision"]
                    or package.get("episode", {}).get("id") != episode.id
                    or package.get("episode", {}).get("target_seconds") != episode.target_seconds
                    or not saved_script.approved_at or saved_script.content != script["content"]):
                raise ConflictError("approved script changed before sound planning")
            plan = ShotPlan.model_validate(event.payload["plan"])
            if sum(shot.duration_seconds for shot in plan.shots) != episode.target_seconds:
                raise ConflictError("confirmed shot duration differs from the episode")
            edit = None
            durations = [shot.duration_seconds for shot in plan.shots]
            if edit_id is not None:
                from .video_tail import VideoTailService
                edits = [e for e in repo.list_run_events(run_id) if e.event_type == "postproduction_edit_drafted"]
                edit = edits[-1] if edits else None
                if (self.data_root is None or edit is None or edit.id != edit_id
                        or edit.payload.get("edit_sha256") != expected_edit_sha256
                        or digest({k: v for k, v in edit.payload.items() if k != "edit_sha256"}) != expected_edit_sha256
                        or edit.payload.get("plan_id") != event.id
                        or edit.payload.get("plan_sha256") != expected_plan_sha256):
                    raise ConflictError("retiming requires the latest matching edit draft")
                timeline = edit.payload["timeline"]
                items = edit.payload["items"]
                if len(timeline) != len(plan.shots) or len(items) != len(plan.shots):
                    raise ConflictError("edited shot inventory changed")
                for item in items:
                    review, media, _ = VideoTailService(repo, self.data_root).accepted_video(run_id, item["review_id"])
                    if review.payload["review_sha256"] != item["review_sha256"] or media.id != item["materialization_id"]:
                        raise ConflictError("adopted media changed before retiming")
                durations = [entry["frame_count"] / edit.payload["frame_rate"] for entry in timeline]
            cues, captions, cursor = [], [], 0
            for index, shot in enumerate(plan.shots):
                end = cursor + durations[index]
                text = " ".join(shot.dialogue_or_narration.split())
                cues.append({"shot_index": index, "start_seconds": cursor, "end_seconds": end,
                             "dialogue_or_narration": shot.dialogue_or_narration, "sound_direction": shot.sound,
                             "speaker_asset_id": None, "voice_authorized": False, "recorded_audio_sha256": None})
                if text:
                    captions.append(f"{len(captions) + 1}\n{srt_time(cursor)} --> {srt_time(end)}\n{html.escape(text)}\n")
                cursor = end
            record = {"run_id": run_id, "episode_id": episode.id, "plan_id": event.id,
                      "plan_sha256": expected_plan_sha256, "production_package_sha256": package["package_sha256"],
                      "duration_seconds": cursor, "cues": cues, "caption_srt_draft": "\n".join(captions),
                      "caption_timing_basis": "CONFIRMED_SHOT_WINDOWS_NOT_SPEECH_ALIGNMENT",
                      "required_audio_layers": ["dialogue", "ambience", "foley", "music", "sfx"],
                      "audio_generated": False, "voice_authorized": False, "speech_alignment_verified": False,
                      "captions_approved": False, "master_accepted": False, "generation_performed": False}
            if edit is not None:
                record.update(edit_id=edit.id, edit_sha256=expected_edit_sha256, edit_approved=False,
                              planned_duration_seconds=episode.target_seconds,
                              caption_timing_basis="DRAFT_EDIT_WINDOWS_NOT_SPEECH_ALIGNMENT")
            record["sound_plan_sha256"] = digest(record)
            for previous in repo.list_run_events(run_id):
                if previous.event_type == "episode_sound_plan_drafted" and previous.payload == record:
                    return previous
            identity = new_id("evt")
            sequence = db.execute("SELECT COALESCE(MAX(sequence),0)+1 FROM run_events WHERE run_id=?", (run_id,)).fetchone()[0]
            db.execute("INSERT INTO run_events VALUES (?,?,?,?,?,?,?,?,?)", (identity, run_id, sequence,
                "episode_sound_plan_drafted", None, None, "Timed sound/caption draft prepared; recordings and alignment remain unverified.", encode(record), utc_now()))
        return repo.get_run_event(identity)
