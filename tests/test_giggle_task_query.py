import httpx
import pytest
from nalu_runtime.giggle_task_query import GiggleTaskQuery, GiggleTaskQueryError


@pytest.mark.parametrize("status", ["pending", "processing", "completed", "failed", "error"])
def test_query_is_read_only_and_does_not_infer_billing(status):
    calls = []
    def serve(request):
        calls.append(request)
        assert request.method == "GET"
        assert request.url.params["task_id"] == "task-fixture"
        assert request.headers["x-auth"] == "synthetic-secret"
        return httpx.Response(200, json={"code": 200, "data": {"status": status,
            "urls": ["https://example.org/fixture.mp4"], "err_msg": "synthetic-secret"}})
    result = GiggleTaskQuery(lambda: "synthetic-secret", transport=httpx.MockTransport(serve)).query("task-fixture")
    assert result.status == status
    assert not result.billing_verified
    assert len(result.result_urls) == (1 if status == "completed" else 0)
    assert "synthetic-secret" not in repr(result)
    assert len(calls) == 1


@pytest.mark.parametrize("data", [
    {"status": "completed", "urls": []},
    {"status": "complete"},
    {"status": "pending", "task_id": "another"},
    {"status": "completed", "urls": ["file:///private/data"]},
    {"status": "completed", "urls": ["https://user:secret@example.org/video"]},
])
def test_ambiguous_or_invalid_responses_do_not_become_completion(data):
    transport = httpx.MockTransport(lambda _: httpx.Response(200, json={"code": 200, "data": data}))
    with pytest.raises(GiggleTaskQueryError):
        GiggleTaskQuery(lambda: "key", transport=transport).query("task-fixture")


def test_redirect_is_not_followed_and_key_is_not_exposed():
    calls = []
    def serve(request):
        calls.append(request)
        return httpx.Response(302, headers={"Location": "https://another.invalid"}, text="synthetic-secret")
    with pytest.raises(GiggleTaskQueryError) as error:
        GiggleTaskQuery(lambda: "synthetic-secret", transport=httpx.MockTransport(serve)).query("task-fixture")
    assert len(calls) == 1
    assert "synthetic-secret" not in str(error.value)
