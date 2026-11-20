"""docs/api-contract.md 의 v0.2·v0.3 예시가 Pydantic 모델과 맞는지 확인한다.

v0.2 추가 경로는 아직 handler.py 에 없으므로, 계약 문서의 JSON 예시를 모델로 직접 검증한다.
"""

import json
import re
from pathlib import Path

import pytest
from pydantic import BaseModel, ValidationError

from app.models.api import (
    AlertsResponse,
    ChatDelta,
    ChatRequest,
    ChatResponse,
    CheckRequest,
    DelayRequest,
    DelayResponse,
    DemoOverride,
    ErrorResponse,
    PhotoTranslateRequest,
    PhotoTranslateResponse,
    PhotoUploadUrlRequest,
    PhotoUploadUrlResponse,
    PlaceScoreBreakdown,
    SpeakRequest,
    SpeakResponse,
    VoiceUrlRequest,
    VoiceUrlResponse,
)

CONTRACT = (Path(__file__).parents[2] / "docs" / "api-contract.md").read_text(encoding="utf-8")


def _section(title: str) -> str:
    """제목(## 또는 ###)부터 다음 제목 전까지의 본문."""
    match = re.search(rf"^#{{2,3}} {re.escape(title)}\n(.*?)(?=^#{{2,3}} |\Z)", CONTRACT, re.M | re.S)
    assert match, f"계약 문서에 '{title}' 절이 없습니다"
    return match.group(1)


def _json_blocks(title: str) -> list[dict]:
    return [json.loads(block) for block in re.findall(r"```json\n(.*?)```", _section(title), re.S)]


# 절 제목 → 그 절의 JSON 예시를 순서대로 검증할 모델
CASES: dict[str, list[type[BaseModel]]] = {
    "데모 스위치": [DemoOverride],
    "POST /plan/{plan_id}/delay": [DelayRequest, DelayResponse],
    "GET /alerts?plan_id=": [AlertsResponse],
    "POST /photo/upload-url": [PhotoUploadUrlRequest, PhotoUploadUrlResponse],
    "POST /photo/translate": [PhotoTranslateRequest, PhotoTranslateResponse],
    "POST /speak": [SpeakRequest, SpeakResponse],
    "POST /voice/url": [VoiceUrlRequest, VoiceUrlResponse],
    "POST /chat score_breakdown": [PlaceScoreBreakdown],
}


@pytest.mark.parametrize("title", CASES)
def test_examples_match_models(title):
    blocks = _json_blocks(title)
    models = CASES[title]
    assert len(blocks) == len(models), f"'{title}' 예시 수가 모델 수와 다릅니다"
    for block, model in zip(blocks, models):
        model.model_validate(block)


def test_stream_delta_example():
    stream = re.search(r"```text\n(.*?)```", _section("스트리밍"), re.S).group(1)
    deltas = re.findall(r"event: delta\ndata: (.*)", stream)
    assert deltas
    for data in deltas:
        ChatDelta.model_validate_json(data)
    assert "event: done" in stream


def test_demo_field_is_optional():
    # 기존 요청은 demo 없이도 그대로 통과한다
    CheckRequest.model_validate({"plan_id": "plan-1"})
    ChatRequest.model_validate({"message": "hi", "profile": {"language": "en"}})
    demo = {"now": "2026-11-28T13:00:00+09:00"}
    assert CheckRequest.model_validate({"plan_id": "plan-1", "demo": demo}).demo.now is not None


@pytest.mark.parametrize("delay_min", [0, -5, 241])
def test_delay_range(delay_min):
    with pytest.raises(ValidationError):
        DelayRequest.model_validate({"plan_id": "plan-1", "delay_min": delay_min})


def test_delay_example_keeps_locked_stop():
    request, response = _json_blocks("POST /plan/{plan_id}/delay")
    changed = {c["stop_id"] for r in response["repairs"] for c in r["changes"]}
    # 샘플 일정의 고정 일정(s2 자갈치시장)은 바뀌지 않는다
    assert "s2" not in changed
    assert request["plan_id"] == response["plan_id"]


def test_example_place_ids_exist():
    places = json.loads(
        (Path(__file__).parents[1] / "app" / "data" / "places.json").read_text(encoding="utf-8")
    )
    known = {p["place_id"] for p in places}
    used = set(re.findall(r'"place_id": "([^"]+)"', _section("v0.2 추가 경로") + CONTRACT))
    assert used <= known, f"places.json 에 없는 장소 ID: {used - known}"


def test_score_breakdown_is_optional():
    # v0.3 필드가 없는 v0.2 응답(고정 응답 샘플 포함)도 그대로 통과하고 빈 목록이 된다
    sample = (Path(__file__).parents[1] / "app" / "data" / "chat_response.json").read_text(encoding="utf-8")
    response = ChatResponse.model_validate_json(sample)
    assert response.score_breakdown == []
    # 비어 있으면 JSON 에 넣지 않는다 (v0.2 응답과 같은 키)
    assert "score_breakdown" not in response.model_dump(mode="json")
    assert "score_breakdown" not in json.loads(response.model_dump_json())


def test_score_breakdown_is_serialized_when_present():
    item = {"place_id": "haeundae-beach", "total": 39.4, "breakdown": {"crowd": 0.0}, "notes": ["crowd:high"]}
    sample = json.loads((Path(__file__).parents[1] / "app" / "data" / "chat_response.json").read_text(encoding="utf-8"))
    response = ChatResponse.model_validate({**sample, "score_breakdown": [item]})
    assert json.loads(response.model_dump_json())["score_breakdown"] == [item]


def test_score_breakdown_matches_ranking_output():
    # 랭킹 엔진 결과를 그대로 옮길 수 있다 (excluded 는 하드 필터용이라 응답에 넣지 않는다)
    import datetime as dt

    from app.models.plan import Profile
    from app.ranking import rank_places
    from tests.guardian_fixtures import make_context

    ctx = make_context()
    ranked = rank_places(["haeundae-beach", "gamcheon-village"], Profile(language="ja", interests=["sea"]), ctx,
                         day=dt.date(2026, 11, 21))
    items = [PlaceScoreBreakdown.model_validate(s.model_dump(exclude={"excluded"})) for s in ranked]
    assert [i.place_id for i in items] == [s.place_id for s in ranked]


def test_score_breakdown_total_range():
    with pytest.raises(ValidationError):
        PlaceScoreBreakdown.model_validate({"place_id": "haeundae-beach", "total": 101, "breakdown": {}})


def test_error_event_uses_error_format():
    ErrorResponse.model_validate({"error": {"code": "internal_error", "message": "오류"}})
