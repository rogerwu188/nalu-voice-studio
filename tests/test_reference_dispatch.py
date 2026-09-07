import httpx
import pytest
from nalu_runtime.asset_service import AssetService
from nalu_runtime.image_budget import ImageBudgetApproval, ImageBudgetService
from nalu_runtime.image_preparation import ImagePreparationService
from nalu_runtime.reference_dispatch import ReferenceDispatchService
from nalu_runtime.repository import ConflictError
from test_reference_image_preparation import reference_plan


@pytest.mark.parametrize("case", ["success", "price_unverified", "changed_plan", "cancelled", "child",
                                  "reduced_budget", "keyframe", "ambiguous", "price_changes_before_http"])
def test_reference_dispatch_binds_real_preparation_and_budget_before_single_attempt(tmp_path, case):
    api, run, plan = reference_plan(tmp_path)
    repo = api.app.state.repository
    assets = AssetService(repo, tmp_path / "data")
    prep_service = ImagePreparationService(repo, assets)
    prepared = (prep_service.prepare_reviewed_shot(run.id, plan.id, 0) if case == "keyframe"
                else prep_service.prepare_reviewed_reference(run.id, plan.id, "grandma"))
    reservation = ImageBudgetService(repo, assets).reserve(run.id, prepared.id, ImageBudgetApproval(
        preparation_sha256=prepared.payload["preparation_sha256"], estimated_credits=10,
        confirmed_run_budget_credits=100, approved_by="Synthetic QA", confirmation="Fixture estimate, not actual spending approval"))
    price_checks, posts, key_reads = [], [], []

    def price_verifier(actual_run, budget, current):
        price_checks.append(current)
        assert actual_run == run.id
        assert budget == reservation.payload
        assert current["preparation_sha256"] == prepared.payload["preparation_sha256"]
        # This is explicitly a synthetic price verifier. Production prices and
        # quote verification are not available or activated by this test.
        if case == "price_unverified" or (case == "price_changes_before_http" and len(price_checks) == 3):
            raise ConflictError("synthetic price unavailable")

    def key():
        key_reads.append(True)
        return "synthetic-not-a-key"

    def http(request):
        posts.append(request)
        if case == "ambiguous":
            raise httpx.ReadTimeout("fixture lost receipt")
        return httpx.Response(200, json={"code": 200, "data": {"task_id": "synthetic-reference"}})

    if case == "changed_plan":
        repo.append_run_event(run.id, "shot_plan_revised", payload={"synthetic": True})
    with repo.db.connect() as db:
        if case == "cancelled":
            db.execute("UPDATE production_runs SET status='cancelled' WHERE id=?", (run.id,))
        if case == "child":
            db.execute("UPDATE projects SET audience_mode='child' WHERE id=?", (run.project_id,))
        if case == "reduced_budget":
            db.execute("UPDATE production_runs SET estimated_budget_credits=5 WHERE id=?", (run.id,))
    service = ReferenceDispatchService(repo, assets)
    kwargs = {"secret": key, "verify_price": price_verifier, "transport": httpx.MockTransport(http)}
    if case in {"price_unverified", "changed_plan", "cancelled", "child", "reduced_budget", "keyframe"}:
        with pytest.raises(ConflictError):
            service.dispatch(run.id, reservation.id, **kwargs)
        assert posts == [] and key_reads == []
        assert not any(e.event_type == "image_submit_intent" for e in repo.list_run_events(run.id))
        return
    result = service.dispatch(run.id, reservation.id, **kwargs)
    assert result.event_type == ("image_task_submitted" if case == "success" else "image_submit_unconfirmed")
    assert len(posts) == (0 if case == "price_changes_before_http" else 1)
    assert len(price_checks) == 3
    before = len(key_reads)
    # Persisted outcome recovery is read-only even after cancellation: it must
    # not create a new attempt just because a quote or project context changed.
    with repo.db.connect() as db:
        db.execute("UPDATE production_runs SET status='cancelled' WHERE id=?", (run.id,))
    assert ReferenceDispatchService(repo, assets).dispatch(run.id, reservation.id, **kwargs).id == result.id
    assert len(key_reads) == before and len(price_checks) == 3
    assert len(posts) == (0 if case == "price_changes_before_http" else 1)
