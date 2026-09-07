from nalu_runtime.postproduction_lineage_qa import _media_stream_facts
from test_video_download import mp4


def test_silent_source_picture_does_not_relax_master_audio_requirement(tmp_path):
    path = tmp_path / "silent-source.mp4"
    path.write_bytes(mp4(frames=12))
    assert _media_stream_facts(path, require_audio=False)["status"] == "PASS"
    master = _media_stream_facts(path)
    assert master["status"] == "FAIL"
    assert "AUDIO_STREAM_MISSING" in master["failures"]
    assert "AUDIO_SAMPLES_MISSING" in master["failures"]
