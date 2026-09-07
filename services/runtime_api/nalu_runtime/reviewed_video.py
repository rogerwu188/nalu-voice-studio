"""Build professional video inputs from reviewed local work, not a user form."""

import base64

from pydantic import BaseModel, ConfigDict, Field

from .image_materialization import ImageMaterializationService
from .qingshan_compilers import ModelCompilerRegistry, project_aspect_ratio
from .repository import ConflictError
from .shot_planning import ShotPlan, ShotPlanningService
from .shot_review import ShotReviewService
from .video_preparation import VideoPreparationRequest, VideoPreparationService, digest


class ReviewedVideoRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_plan_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    shot_index: int = Field(strict=True, ge=0, le=119)
    approved_frame_review_id: str = Field(min_length=1, max_length=160)


class ReviewedVideoService:
    def __init__(self, repository, data_root):
        self.repository, self.data_root = repository, data_root

    def prepare(self, run_id, plan_id, incoming: ReviewedVideoRequest):
        request = self.compose(run_id, plan_id, incoming)
        # This revalidates under the same writer lock as frame decisions and
        # snapshot refresh. No provider submission or spending approval occurs.
        return VideoPreparationService(self.repository).prepare(run_id, request)

    def compose(self, run_id, plan_id, incoming: ReviewedVideoRequest):
        repo = self.repository
        run = repo.get_run(run_id)
        package = ShotPlanningService(repo)._package(run)
        event = ShotReviewService(repo).current(run_id)
        if event is None or event.id != plan_id or event.event_type != "shot_plan_approved":
            raise ConflictError("confirm the current shot plan before preparing video")
        record = event.payload
        if (record.get("approved") is not True or record.get("plan_sha256") != incoming.expected_plan_sha256
                or digest({k: v for k, v in record.items() if k != "plan_sha256"}) != incoming.expected_plan_sha256
                or record.get("production_package_sha256") != package["package_sha256"]):
            raise ConflictError("reviewed plan or production snapshot changed")
        plan = ShotPlan.model_validate(record["plan"])
        episode = repo.get_episode(run.episode_id)
        script = package.get("approved_script", {})
        if (record.get("script_revision") != episode.approved_script_revision
                or script.get("revision") != episode.approved_script_revision
                or sum(shot.duration_seconds for shot in plan.shots) != episode.target_seconds):
            raise ConflictError("episode script or duration changed; reconcile its approved shots first")
        if incoming.shot_index >= len(plan.shots):
            raise ConflictError("shot does not exist in the reviewed episode")
        shot = plan.shots[incoming.shot_index]
        if shot.director is None:
            raise ConflictError("finish and confirm this shot's camera and action choices first")
        if shot.transition == "continuous":
            raise ConflictError("continuous shot requires the previous accepted final frame, not a newly generated opening image")
        tasks = [task for task in record.get("tasks", []) if task.get("shot_index") == incoming.shot_index]
        if len(tasks) != 1:
            raise ConflictError("reviewed shot task identity is missing or ambiguous")
        task_key = tasks[0]["task_key"]
        review = repo.get_run_event(incoming.approved_frame_review_id)
        frame = review.payload
        if (review.run_id != run_id or review.event_type != "image_frame_reviewed"
                or frame.get("task_key") != task_key + "-entry" or frame.get("decision") != "accept"
                or frame.get("user_approved") is not True
                or frame.get("approved_plan_event_id") != plan_id
                or frame.get("approved_plan_sha256") != incoming.expected_plan_sha256
                or frame.get("review_sha256") != digest({k: v for k, v in frame.items() if k != "review_sha256"})):
            raise ConflictError("confirm this shot's exact opening image first")
        materialized, raw = ImageMaterializationService(repo, self.data_root).read_saved(run_id, frame["materialization_id"])
        if (materialized.payload.get("materialization_sha256") != frame.get("materialization_sha256")
                or materialized.payload["image"]["sha256"] != frame.get("image_sha256")):
            raise ConflictError("saved image differs from its confirmation")
        compiler = ModelCompilerRegistry().compiler_for(run.requested_model)
        # The existing concrete transport supports SD2 image-to-video only. Never
        # disguise another model or silently omit its required omni references.
        if compiler.model != "seedance-2.0-pro":
            raise ConflictError("this model requires its own concrete reviewed video transport")
        request = {"model": compiler.model, "provider_model_id": compiler.model,
                   "adapter_id": compiler.adapter_id, "profile_id": compiler.profile_id,
                   "prompt": shot.video_prompt, "duration_seconds": shot.duration_seconds,
                   "native_resolution_contract": compiler.native_resolution,
                   "delivery_resolution_contract": compiler.native_resolution,
                   "native_resolution_must_remain_honestly_labeled": True, "silent_upscale_forbidden": True,
                   "shot_role": "SCENE_FIRST", "opening_anchor": {
                       "kind": "GENERATED_ENTRY_KEYFRAME", "generation_state": "ENTRY_STATE_ONLY",
                       "frame_sha256": frame["image_sha256"]},
                   "video_transport": {"mode": "image_to_video_start_frame", "aspect_ratio": project_aspect_ratio(package),
                                       "start_frame": {"base64": base64.b64encode(raw).decode()}}}
        # VideoPreparationService compiles the exact reviewed director and scope.
        # Do not manufacture prop visual QA or previous-episode continuity evidence.
        return VideoPreparationRequest(task_key=task_key, request=request, approved_plan_event_id=plan_id,
            approved_plan_sha256=incoming.expected_plan_sha256, approved_frame_review_id=review.id)
