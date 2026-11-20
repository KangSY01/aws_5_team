"""평가 질의셋(backend/eval/queries.json)이 모델·샘플 데이터와 맞는지 확인한다."""

import json
from pathlib import Path

import pytest

from app.handler import PLACES, SAMPLE_PLAN
from app.models.plan import Profile

QUERIES = json.loads((Path(__file__).parents[1] / "eval" / "queries.json").read_text(encoding="utf-8"))
PLACE_IDS = {p.place_id for p in PLACES}
CATEGORIES = {"plan_create", "plan_edit", "recommend", "place_detail", "route", "food", "event", "safety", "guardian"}


def test_ids_unique_and_ordered():
    assert [q["id"] for q in QUERIES] == list(range(1, len(QUERIES) + 1))


@pytest.mark.parametrize("q", QUERIES, ids=lambda q: f"q{q['id']}")
def test_query_shape(q):
    assert q["category"] in CATEGORIES
    assert q["plan_id"] in (None, SAMPLE_PLAN.plan_id)
    # 장소 ID는 places.json 에 있는 값만
    assert set(q["expect"]["places_any"]) <= PLACE_IDS
    if q["endpoint"] == "/chat":
        assert q["message"]
        Profile.model_validate(q["profile"])
    else:
        assert q["endpoint"] == "/plan/check"
        assert q["plan_id"] is not None


def test_safety_and_preservation_cases_exist():
    # 채점 목표: 안전 처리 2건, 일정 보전 3건(19·20·21)
    assert sum(q["category"] == "safety" for q in QUERIES) == 2
    assert {19, 20, 21} <= {q["id"] for q in QUERIES}


def test_q10_places_any_is_every_indoor_place():
    # 10번(비 올 때 실내 장소)은 실내 장소 중 하나라도 답하면 맞다. 일부만 두면 맞는 답도 실패로 채점된다
    q10 = next(q for q in QUERIES if q["id"] == 10)
    assert set(q10["expect"]["places_any"]) == {p.place_id for p in PLACES if p.indoor}
