from types import SimpleNamespace

import pytest
from nalu_runtime.models import RunStatus
from nalu_runtime.repository import ConflictError
from nalu_runtime.video_preparation import VideoPreparationService


@pytest.mark.parametrize("status", [RunStatus.RUNNING, RunStatus.QA_REVIEW, RunStatus.CANCELLED])
def test_postproduction_does_not_enable_new_preparation(status):
    repo = SimpleNamespace(get_run=lambda _: SimpleNamespace(status=status, project_id="project"),
                           get_project=lambda _: SimpleNamespace(archived_at=None))
    with pytest.raises(ConflictError, match="shot preparation requires"):
        VideoPreparationService(repo).validate("run", SimpleNamespace())


def test_saved_video_read_still_refuses_superseded_run():
    repo = SimpleNamespace(get_run=lambda _: SimpleNamespace(status=RunStatus.RUNNING,
        project_id="project", episode_id="episode"), get_project=lambda _: SimpleNamespace(archived_at=None),
        latest_run_for_episode=lambda _: SimpleNamespace(id="newer"))
    with pytest.raises(ConflictError, match="superseded"):
        VideoPreparationService(repo).validate("run", SimpleNamespace(), _read_saved=True)
