from __future__ import annotations

import re
from dataclasses import dataclass, field

from .models import (
    CharacterContinuityState,
    ContinuityExtractionEvidence,
    ContinuityState,
    PropContinuityState,
)

_ENDING_CUES = ("尾声", "结尾", "最后一幕", "终场", "片尾")
_LOCATION_SUFFIXES = (
    "旧火车站",
    "火车站",
    "车站",
    "码头",
    "机场",
    "医院",
    "学校",
    "教室",
    "办公室",
    "工厂",
    "公园",
    "墓园",
    "广场",
    "山顶",
    "海边",
    "客厅",
    "厨房",
    "卧室",
    "院子",
    "老家",
    "家中",
    "家里",
)
_WEATHER_TERMS = (
    "暴风雪",
    "大雪",
    "小雪",
    "暴雨",
    "大雨",
    "小雨",
    "雷雨",
    "细雨",
    "晴朗",
    "晴天",
    "阴天",
    "多云",
    "大雾",
    "浓雾",
)
_TIME_PATTERN = re.compile(
    r"(?P<value>(?:19|20)\d{2}\s*年(?:[^，。；！？\n]{0,10})|"
    r"次日清晨|第二天清晨|当天夜里|当天晚上|冬夜|夏夜|深夜|夜里|晚上|"
    r"黄昏|傍晚|清晨|黎明|正午)"
)
_SUBJECT = r"(?P<name>[\u4e00-\u9fff·]{1,8})"
_LOCATION = rf"(?P<location>[\u4e00-\u9fffA-Za-z0-9·]{{0,12}}(?:{'|'.join(_LOCATION_SUFFIXES)}))"
_SEGMENT_START = r"(?:^|[，。；！？：\n])\s*"
_GENERIC_SUBJECTS = {
    "他",
    "她",
    "他们",
    "她们",
    "老人",
    "孩子",
    "镜头",
    "画面",
    "众人",
    "大家",
}


@dataclass
class SemanticContinuityResult:
    state: ContinuityState
    unresolved_hooks: list[str] = field(default_factory=list)
    evidence: list[ContinuityExtractionEvidence] = field(default_factory=list)


def _ending_window(content: str) -> str:
    """Return a bounded final-scene window so earlier facts cannot leak forward."""

    tail = content[-4000:]
    cue_positions = [tail.rfind(cue) for cue in _ENDING_CUES]
    last_cue = max(cue_positions)
    if last_cue >= 0:
        return tail[last_cue:]
    # Legacy prose often lacks scene headings. Five hundred final characters are
    # enough for a handoff while remaining deliberately conservative.
    return tail[-500:]


def _excerpt(window: str, start: int, end: int) -> str:
    left = max(0, window.rfind("\n", 0, start) + 1)
    if end > 0 and window[end - 1] in "。！？\n":
        return window[left:end].strip()[:300]
    stops = [
        position
        for mark in ("。", "！", "？", "\n")
        if (position := window.find(mark, end)) >= 0
    ]
    right = min(stops) + 1 if stops else min(len(window), end + 80)
    return window[left:right].strip()[:300]


def _add_evidence(
    evidence: list[ContinuityExtractionEvidence],
    *,
    path: str,
    excerpt: str,
    rule: str,
    confidence: str = "high",
) -> None:
    if any(item.path == path and item.excerpt == excerpt for item in evidence):
        return
    evidence.append(
        ContinuityExtractionEvidence(
            path=path,
            excerpt=excerpt,
            rule=rule,
            confidence=confidence,
        )
    )


def _clean_name(value: str) -> str | None:
    name = value.strip(" ，。；！？：\n")
    if not name or name in _GENERIC_SUBJECTS:
        return None
    return name


def _clean_object(value: str) -> str:
    return value.strip(" ，。；！？：‘’“”了着")


def extract_semantic_ending_continuity(content: str) -> SemanticContinuityResult:
    """Conservatively propose end-state facts from unstructured Chinese prose.

    This is intentionally a deterministic proposal generator, not narrative
    authority. It only reads the final scene, requires explicit grammatical cues,
    and returns exact evidence for the later readback and confirmation step.
    """

    window = _ending_window(content)
    evidence: list[ContinuityExtractionEvidence] = []
    characters: dict[str, CharacterContinuityState] = {}
    props: dict[str, PropContinuityState] = {}

    location_matches = list(
        re.finditer(
            rf"(?:站在|留在|来到|回到|走进|停在|坐在|躺在|出现在)\s*{_LOCATION}",
            window,
        )
    )
    scene_location = None
    if location_matches:
        match = location_matches[-1]
        scene_location = match.group("location").strip()
        _add_evidence(
            evidence,
            path="scene_location",
            excerpt=_excerpt(window, match.start(), match.end()),
            rule="explicit_final_scene_location",
        )

    weather_matches = [
        match
        for term in _WEATHER_TERMS
        for match in re.finditer(re.escape(term), window)
        if re.search(
            rf"(?:天气|下起|下着|飘着|变成|转为|依然|仍然|窗外|夜里)[^。！？\n]{{0,10}}{re.escape(term)}",
            window[max(0, match.start() - 16) : match.end()],
        )
        or term in {"晴朗", "晴天", "阴天", "多云"}
    ]
    weather = None
    if weather_matches:
        match = max(weather_matches, key=lambda item: item.start())
        weather = match.group(0)
        _add_evidence(
            evidence,
            path="weather",
            excerpt=_excerpt(window, match.start(), match.end()),
            rule="explicit_weather_phrase",
        )

    time_matches = list(_TIME_PATTERN.finditer(window))
    story_time = None
    if time_matches:
        dated_matches = [match for match in time_matches if "年" in match.group("value")]
        match = dated_matches[-1] if dated_matches else time_matches[-1]
        story_time = re.sub(r"\s+", " ", match.group("value").strip())
        _add_evidence(
            evidence,
            path="story_time",
            excerpt=_excerpt(window, match.start(), match.end()),
            rule="explicit_time_phrase",
        )

    character_location_pattern = re.compile(
        rf"{_SEGMENT_START}{_SUBJECT}(?:站在|留在|来到|回到|走进|停在|坐在|躺在|出现在)\s*{_LOCATION}"
    )
    for match in character_location_pattern.finditer(window):
        name = _clean_name(match.group("name"))
        if not name:
            continue
        character = characters.setdefault(name, CharacterContinuityState())
        character.location = match.group("location").strip()
        _add_evidence(
            evidence,
            path=f"characters.{name}.location",
            excerpt=_excerpt(window, match.start(), match.end()),
            rule="named_character_location",
        )

    wardrobe_pattern = re.compile(
        rf"{_SEGMENT_START}{_SUBJECT}(?:身穿|穿着)\s*(?P<value>[^，。；！？\n]{{1,30}})"
    )
    for match in wardrobe_pattern.finditer(window):
        name = _clean_name(match.group("name"))
        value = _clean_object(match.group("value"))
        if not name or not value:
            continue
        character = characters.setdefault(name, CharacterContinuityState())
        character.wardrobe = [value]
        _add_evidence(
            evidence,
            path=f"characters.{name}.wardrobe",
            excerpt=_excerpt(window, match.start(), match.end()),
            rule="named_character_wardrobe",
        )

    held_prop_pattern = re.compile(
        rf"{_SEGMENT_START}{_SUBJECT}(?:提着|拿着|抱着|握着|拎着|背着)\s*(?P<value>[^，。；！？\n]{{1,24}})"
    )
    for match in held_prop_pattern.finditer(window):
        name = _clean_name(match.group("name"))
        value = _clean_object(match.group("value"))
        if not name or not value:
            continue
        character = characters.setdefault(name, CharacterContinuityState())
        character.held_props = [value]
        props.setdefault(value, PropContinuityState(owner=name, location=character.location))
        _add_evidence(
            evidence,
            path=f"characters.{name}.held_props",
            excerpt=_excerpt(window, match.start(), match.end()),
            rule="named_character_held_prop",
        )
        _add_evidence(
            evidence,
            path=f"props.{value}.owner",
            excerpt=_excerpt(window, match.start(), match.end()),
            rule="held_prop_owner",
        )

    injury_pattern = re.compile(
        rf"{_SEGMENT_START}(?P<name>[\u4e00-\u9fff·]{{1,8}}?)"
        r"(?P<value>(?:的)?(?:左手|右手|左腿|右腿|手臂|腿|额头|头部|肩膀|后背)"
        r"[^，。；！？\n]{0,8}(?:受伤|包扎|缠着绷带|流着血)[^，。；！？\n]{0,8})"
    )
    for match in injury_pattern.finditer(window):
        name = _clean_name(match.group("name"))
        value = _clean_object(match.group("value")).removeprefix("的")
        if not name or not value:
            continue
        character = characters.setdefault(name, CharacterContinuityState())
        character.injuries = [value]
        _add_evidence(
            evidence,
            path=f"characters.{name}.injuries",
            excerpt=_excerpt(window, match.start(), match.end()),
            rule="named_character_injury",
        )

    revealed_pattern = re.compile(
        rf"{_SEGMENT_START}(?P<name>[\u4e00-\u9fff·]{{1,8}}?)"
        r"(?:终于|已经)?(?:知道|得知|发现|明白)(?:了)?\s*"
        r"(?P<value>[^。；！？\n]{2,80})"
    )
    for match in revealed_pattern.finditer(window):
        name = _clean_name(match.group("name"))
        value = _clean_object(match.group("value"))
        if not name or not value:
            continue
        character = characters.setdefault(name, CharacterContinuityState())
        character.revealed_facts = [value]
        _add_evidence(
            evidence,
            path=f"characters.{name}.revealed_facts",
            excerpt=_excerpt(window, match.start(), match.end()),
            rule="named_character_revelation",
        )

    unresolved_hooks: list[str] = []
    for match in re.finditer(r"(?P<sentence>[^。！？\n]{2,140}[？?])", window):
        sentence = match.group("sentence").strip(" ，。；！？：\n")
        if not any(cue in sentence for cue in ("是否", "会不会", "究竟", "真相", "秘密")):
            continue
        unresolved_hooks.append(sentence)
        _add_evidence(
            evidence,
            path="unresolved_hooks",
            excerpt=_excerpt(window, match.start(), match.end()),
            rule="explicit_unresolved_question",
            confidence="medium",
        )
    for match in re.finditer(
        r"(?P<sentence>[^。！？\n]{2,140}(?:仍是个谜|还是个谜|尚未揭晓|无人知道))",
        window,
    ):
        sentence = match.group("sentence").strip(" ，。；！？：\n")
        if sentence not in unresolved_hooks:
            unresolved_hooks.append(sentence)
            _add_evidence(
                evidence,
                path="unresolved_hooks",
                excerpt=_excerpt(window, match.start(), match.end()),
                rule="explicit_unresolved_statement",
                confidence="medium",
            )

    # A held prop inherits the final scene only when its named holder has that exact
    # location; this avoids guessing a prop location from a nearby scene description.
    for name, character in characters.items():
        for prop_name in character.held_props or []:
            if character.location and prop_name in props:
                props[prop_name].location = character.location

    return SemanticContinuityResult(
        state=ContinuityState(
            characters=characters,
            props=props,
            scene_location=scene_location,
            story_time=story_time,
            weather=weather,
        ),
        unresolved_hooks=list(dict.fromkeys(unresolved_hooks)),
        evidence=evidence,
    )
