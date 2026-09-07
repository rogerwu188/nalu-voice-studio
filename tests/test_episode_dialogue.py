import io
import wave

import pytest
from nalu_runtime.episode_dialogue import assemble_dialogue
from nalu_runtime.repository import ConflictError


def part(start, value):
    output = io.BytesIO()
    with wave.open(output, "wb") as target:
        target.setnchannels(2); target.setsampwidth(2); target.setframerate(48000)
        target.writeframes(value.to_bytes(2, "little", signed=True) * 2 * 48000)
    return {"start_seconds": start, "sample_count": 48000, "audio": output.getvalue(),
            "segments": [{"start_seconds": 0.1, "end_seconds": 0.9, "text": "回忆"}]}


def test_dialogue_joins_real_pcm_and_offsets_each_caption():
    audio, captions = assemble_dialogue([part(0, 100), part(1, -200)], 2)
    with wave.open(io.BytesIO(audio), "rb") as source:
        assert source.getnframes() == 96000
        assert source.readframes(1) == b"\x64\x00" * 2
        source.setpos(48000)
        assert source.readframes(1) == b"\x38\xff" * 2
    assert b"00:00:00.100 --> 00:00:00.900" in captions
    assert b"00:00:01.100 --> 00:00:01.900" in captions
    assert captions.count(b"WEBVTT") == 1


@pytest.mark.parametrize("parts,duration", [([], 1), ([part(0, 1)], 2),
    ([part(0, 1), part(1.1, 2)], 2), ([part(0, 1), part(0.9, 2)], 2),
    ([part(0, 1)], 0.5)])
def test_dialogue_never_pads_missing_or_overlapping_recordings(parts, duration):
    with pytest.raises(ConflictError):
        assemble_dialogue(parts, duration)
