from __future__ import annotations

import tracemalloc
from array import array
from fractions import Fraction
from pathlib import Path

import av
from nalu_runtime import postproduction_materializer


def write_long_pcm_fixture(
    path: Path,
    *,
    duration_seconds: int,
    stereo_values: tuple[int, int] = (1000, -1000),
) -> None:
    sample_rate = postproduction_materializer.AUDIO_SAMPLE_RATE
    with av.open(str(path), mode="w", format="wav") as container:
        stream = container.add_stream("pcm_s16le", rate=sample_rate)
        stream.layout = "stereo"
        cursor = 0
        total = duration_seconds * sample_rate
        while cursor < total:
            samples = min(4096, total - cursor)
            frame = av.AudioFrame(format="s16", layout="stereo", samples=samples)
            frame.sample_rate = sample_rate
            frame.pts = cursor
            frame.time_base = Fraction(1, sample_rate)
            frame.planes[0].update((array("h", stereo_values) * samples).tobytes())
            for packet in stream.encode(frame):
                container.mux(packet)
            cursor += samples
        for packet in stream.encode(None):
            container.mux(packet)


def test_long_audio_decode_has_fixed_chunk_and_python_heap_bounds(tmp_path: Path) -> None:
    duration_seconds = 90
    source = tmp_path / "ninety-seconds.wav"
    write_long_pcm_fixture(source, duration_seconds=duration_seconds)

    tracemalloc.start()
    try:
        total_values = 0
        largest_chunk = 0
        for chunk in postproduction_materializer._audio_chunks(
            source,
            start_seconds=0,
            sample_count=duration_seconds * postproduction_materializer.AUDIO_SAMPLE_RATE,
            require_full_duration=True,
        ):
            total_values += len(chunk)
            largest_chunk = max(largest_chunk, len(chunk))
        _current, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    assert total_values == (
        duration_seconds
        * postproduction_materializer.AUDIO_SAMPLE_RATE
        * postproduction_materializer.AUDIO_CHANNELS
    )
    assert largest_chunk <= (
        postproduction_materializer.AUDIO_CHUNK_SAMPLES * postproduction_materializer.AUDIO_CHANNELS
    )
    assert peak < 4 * 1024 * 1024


def test_vectorized_five_stem_mix_preserves_scalar_contract(tmp_path: Path) -> None:
    duration_seconds = 1
    gains = [1.0, 0.75, 0.5, 0.25, 0.125]
    values = [
        (1000, -1000),
        (2000, -2000),
        (-500, 500),
        (300, -300),
        (-100, 100),
    ]
    stems: list[tuple[Path, float]] = []
    for index, (stereo_values, gain) in enumerate(zip(values, gains, strict=True)):
        path = tmp_path / f"stem-{index}.wav"
        write_long_pcm_fixture(
            path,
            duration_seconds=duration_seconds,
            stereo_values=stereo_values,
        )
        stems.append((path, gain))

    mixed = array("h")
    for chunk in postproduction_materializer._mixed_audio_chunks(
        stems,
        sample_count=duration_seconds * postproduction_materializer.AUDIO_SAMPLE_RATE,
    ):
        mixed.extend(chunk)

    total_gain = sum(gains)
    expected_left = round(
        sum(stereo[0] * gain for stereo, gain in zip(values, gains, strict=True))
        / total_gain
        * 0.9
    )
    expected_right = round(
        sum(stereo[1] * gain for stereo, gain in zip(values, gains, strict=True))
        / total_gain
        * 0.9
    )
    assert len(mixed) == (
        duration_seconds
        * postproduction_materializer.AUDIO_SAMPLE_RATE
        * postproduction_materializer.AUDIO_CHANNELS
    )
    assert mixed == array("h", [expected_left, expected_right]) * (
        duration_seconds * postproduction_materializer.AUDIO_SAMPLE_RATE
    )
