import pytest
from nalu_runtime.episode_transcript import caption_vtt
from nalu_runtime.repository import ConflictError


def test_caption_vtt_offsets_and_escapes_literal_text():
    result = caption_vtt([{"start_seconds": 0.1, "end_seconds": 1.2,
                           "text": "<v narrator>老照片 &\n\n家人 -->"}], 7.5).decode()
    assert "00:00:07.600 --> 00:00:08.700" in result
    assert "&lt;v narrator&gt;老照片 &amp; 家人 --&gt;" in result
    assert result.startswith("WEBVTT\n\n")


@pytest.mark.parametrize("offset,start,end", [(float("nan"), 0, 1), (-1, 0, 1),
    (1800, 0, 1), (0, 0.0001, 0.0002)])
def test_unrepresentable_caption_timing_is_rejected(offset, start, end):
    with pytest.raises(ConflictError):
        caption_vtt([{"start_seconds": start, "end_seconds": end, "text": "字幕"}], offset)
