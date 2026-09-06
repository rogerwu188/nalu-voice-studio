"""Dispatch only a persisted, reviewed shot via the durable single-attempt boundary."""

import httpx

from .giggle_video_transport import GiggleSeedanceImageTransport
from .models import RemoteTaskState
from .remote_submitter import DurableRemoteTaskSubmitter
from .repository import ConflictError, Repository
from .video_budget import VideoBudgetApproval, VideoBudgetService
from .video_preparation import VideoPreparationRequest, VideoPreparationService, digest


class VideoDispatchService:
    def __init__(self, repository: Repository, submitter: DurableRemoteTaskSubmitter,
                 transport: httpx.BaseTransport | None = None):
        self.repository, self.submitter, self.transport = repository, submitter, transport

    def dispatch(self, run_id: str, reservation_id: str, secret: str):
        event = self.repository.get_run_event(reservation_id)
        if event.run_id != run_id or event.event_type != "video_estimate_reserved":
            raise ConflictError("reservation does not belong to this run")
        reservation = event.payload
        if (reservation.get("run_id") != run_id or reservation.get("reservation_sha256") !=
                digest({k: v for k, v in reservation.items() if k != "reservation_sha256"})):
            raise ConflictError("reservation integrity or import boundary failed")
        # A repeated click after submission/uncertainty is read-only, even after
        # the quote expires or the user cancels. Never manufacture another task.
        existing = [item for item in self.repository.list_remote_task_bindings(run_id)
                    if item.task_key == reservation["task_key"]]
        if existing:
            if len(existing) != 1 or existing[0].request_sha256 != reservation["request_sha256"]:
                raise ConflictError("saved task differs from reserved shot")
            if existing[0].state != RemoteTaskState.PREPARED:
                return existing[0]
        if not reservation.get("pricing_quote_id") or not reservation.get("published_price_observed"):
            raise ConflictError("dispatch requires a reviewed observed-price estimate")
        approval = VideoBudgetApproval.model_validate({
            key: reservation[key] for key in VideoBudgetApproval.model_fields if key in reservation})
        VideoBudgetService(self.repository).reserve(run_id, reservation["preparation_id"], approval)
        prepared_event = self.repository.get_run_event(reservation["preparation_id"])
        prepared = prepared_event.payload
        prepared_request = VideoPreparationRequest(
            task_key=prepared["task_key"], request=prepared["request"],
            approved_plan_event_id=prepared.get("approved_plan_event_id"),
            approved_plan_sha256=prepared.get("approved_plan_sha256"))
        verified = VideoPreparationService(self.repository).validate(run_id, prepared_request)
        if verified["preparation_sha256"] != reservation["preparation_sha256"]:
            raise ConflictError("prepared shot changed after approval")
        package_sha, package = self.submitter._authorized_package(run_id, "seedance-2.0-pro")
        if package_sha != reservation["production_package_sha256"]:
            raise ConflictError("approved production package changed")
        self._validate_current_context(run_id, package, reservation)
        def before_submit():
            # Recheck after the durable intent and immediately before HTTP.
            VideoBudgetService(self.repository).reserve(run_id, reservation["preparation_id"], approval)
            current_sha, current_package = self.submitter._authorized_package(run_id, "seedance-2.0-pro")
            if current_sha != package_sha:
                raise ConflictError("package changed during dispatch")
            VideoPreparationService(self.repository)._plan_binding(run_id, prepared_request, current_sha)
            self._validate_current_context(run_id, current_package, reservation)
        transport = GiggleSeedanceImageTransport(lambda: secret, transport=self.transport, before_submit=before_submit)
        return self.submitter.submit_paid_task(
            run_id, task_key=prepared["task_key"], provider="giggle", model="seedance-2.0-pro",
            request=prepared["request"], transport=transport,
        )

    def _validate_current_context(self, run_id, package, reservation):
        run = self.repository.get_run(run_id)
        episode = self.repository.get_episode(run.episode_id)
        latest = self.repository.latest_run_for_episode(run.episode_id)
        script_data = package.get("approved_script", {})
        revision = script_data.get("revision")
        if (latest is None or latest.id != run_id or type(revision) is not int
                or episode.approved_script_revision != revision
                or episode.status not in {"script_approved", "preproduction", "generating"}
                or package.get("episode", {}).get("id") != episode.id
                or package.get("project", {}).get("id") != run.project_id
                or package.get("season", {}).get("id") != run.season_id):
            raise ConflictError("current approved episode differs from production package")
        script = self.repository.get_script(episode.id, revision)
        if not script.approved_at or script.content != script_data.get("content"):
            raise ConflictError("script approval was revoked or content changed")
        if package["production_policy"].get("estimated_budget_credits") != reservation["confirmed_run_budget_credits"]:
            raise ConflictError("package budget differs from confirmed budget")
        project = self.repository.get_project(run.project_id)
        current_assets = self.repository.list_assets(run.project_id, episode.id)
        snapshots = {item["id"]: item for item in package.get("inherited_assets", [])}
        if set(snapshots) != {asset.id for asset in current_assets}:
            raise ConflictError("episode assets changed; prepare and review again")
        for asset in current_assets:
            if asset.kind in {"character_image", "voice_reference"} and (
                not asset.consent_granted or (project.audience_mode == "child" and not asset.guardian_approved)
            ):
                raise ConflictError("biometric permission missing or revoked")
            if asset.metadata.get("sha256") != snapshots[asset.id].get("metadata", {}).get("sha256"):
                raise ConflictError("approved asset bytes changed")
        if digest(self.repository.resolved_project_library(run.project_id)) != digest(package.get("resolved_library", [])):
            raise ConflictError("project library changed after production approval")
