"""app/chat 보조 모듈 단위 테스트: 고정 문장, 일정 검증, 답변 검증, sources, 일정 생성 도구. AWS·네트워크 없음."""

import datetime as dt
import json
from pathlib import Path

import pytest

from app.chat import answer as chat_answer
from app.chat import tools as chat_tools
from app.chat.messages import BUILD_ERROR_KEYS, LANGUAGES, MESSAGES, message
from app.chat.plan_rules import load_places, place_name, validate_plan
from app.chat.tools import MAX_TOOL_CALLS, PlanCreator, ToolOutput
from app.models.plan import Plan, Profile
from app.tools.schedule import PlanBuildError

SAMPLE = Plan.model_validate_json((Path(__file__).parents[1] / "app" / "data" / "sample_plan.json").read_text(encoding="utf-8"))
KST = dt.timezone(dt.timedelta(hours=9))
ALL = {"haeundae-beach", "gamcheon-village", "busan-tower", "jagalchi-market", "gwangalli-beach"}
FIVE = ["haeundae-beach", "gamcheon-village", "busan-tower", "jagalchi-market", "gwangalli-beach"]


def at(hour: int, minute: int = 0) -> dt.datetime:
    return dt.datetime(2026, 11, 21, hour, minute, tzinfo=KST)


# ---- 고정 문장 ----


def test_every_message_exists_in_all_four_languages():
    for key, by_language in MESSAGES.items():
        assert set(by_language) == set(LANGUAGES), key
        assert all(text.strip() for text in by_language.values()), key


@pytest.mark.parametrize("language", LANGUAGES)
def test_message_formatting_keeps_placeholders_filled(language):
    text = message("plan_created", language, count=3, date="2026-11-28", places="A, B, C")
    assert "{" not in text and "2026-11-28" in text and "A, B, C" in text
    assert "{" not in message("source_travel", language, origin="A", destination="B")


def test_build_error_keys_all_have_messages():
    assert BUILD_ERROR_KEYS <= set(MESSAGES)


# ---- 장소 이름 ----


def test_place_name_falls_back_to_other_languages():
    places = load_places()
    assert place_name(places["haeundae-beach"], "ja") == places["haeundae-beach"].names["ja"]
    partial = places["the-bay-101"]  # ja 이름이 없다
    assert place_name(partial, "ja") == partial.names["en"]
    nameless = partial.model_copy(update={"names": {}})
    assert place_name(nameless, "en") == "the-bay-101"


# ---- validate_plan ----


def with_stop(plan: Plan, stop_id: str, **update) -> Plan:
    return plan.model_copy(update={"stops": [s.model_copy(update=update) if s.stop_id == stop_id else s for s in plan.stops]})


def test_validate_plan_accepts_the_sample_and_touching_stops():
    assert validate_plan(SAMPLE) == []
    assert validate_plan(with_stop(SAMPLE, "s1", end=at(12))) == []  # 앞 Stop 이 끝나는 시각에 다음 Stop 이 시작


@pytest.mark.parametrize(
    "plan, code",
    [
        (with_stop(SAMPLE, "s3", start=at(12, 30)), "overlap"),
        (with_stop(SAMPLE, "s3", start=at(15), end=at(14)), "bad_time_range"),
        (with_stop(SAMPLE, "s3", start=at(14), end=at(14)), "bad_time_range"),
        (with_stop(SAMPLE, "s3", place_id="no-such-place"), "unknown_place"),
        (SAMPLE.model_copy(update={"stops": [*SAMPLE.stops, SAMPLE.stops[0]]}), "duplicate_stop_id"),
    ],
)
def test_validate_plan_reports_problems(plan, code):
    assert code in validate_plan(plan)


def test_validate_plan_protects_locked_stops_against_the_original():
    assert "locked_changed" in validate_plan(with_stop(SAMPLE, "s2", place_id="gwangalli-beach"), original=SAMPLE)
    assert "locked_changed" in validate_plan(with_stop(SAMPLE, "s2", start=at(12, 10)), original=SAMPLE)
    removed = SAMPLE.model_copy(update={"stops": [s for s in SAMPLE.stops if s.stop_id != "s2"]})
    assert "locked_changed" in validate_plan(removed, original=SAMPLE)
    assert validate_plan(with_stop(SAMPLE, "s4", place_id="gwangalli-beach"), original=SAMPLE) == []


# ---- render_answer ----


@pytest.mark.parametrize("language", LANGUAGES)
def test_render_answer_replaces_markers_with_names_in_the_profile_language(language):
    text = chat_answer.render_answer("Go to [place:haeundae-beach] and [place: busan-tower ].", language, ALL)
    places = load_places()
    assert place_name(places["haeundae-beach"], language) in text
    assert place_name(places["busan-tower"], language) in text
    assert "[place" not in text


def test_render_answer_rejects_ids_without_grounds():
    with pytest.raises(chat_answer.InvalidAnswer):
        chat_answer.render_answer("Visit [place:taejongdae]", "en", ALL)  # places.json 에는 있지만 이번 요청의 근거가 아니다
    with pytest.raises(chat_answer.InvalidAnswer):
        chat_answer.render_answer("Visit [place:made-up-place]", "en", ALL | {"made-up-place"})  # 없는 장소


def test_render_answer_rejects_ungrounded_place_names_written_without_markers():
    taejongdae = place_name(load_places()["taejongdae"], "en")
    with pytest.raises(chat_answer.InvalidAnswer):
        chat_answer.render_answer(f"You could also see {taejongdae}.", "en", ALL)
    assert taejongdae in chat_answer.render_answer(f"See {taejongdae}.", "en", ALL | {"taejongdae"})  # 근거가 있으면 된다


def test_render_answer_ignores_grounded_names_inside_longer_ungrounded_names(monkeypatch):
    # 근거 있는 이름이 근거 없는 장소 이름의 일부여도 오탐하지 않는다
    places = load_places()
    longer = places["busan-tower"].model_copy(update={"place_id": "busan-tower-annex", "names": {"en": "Busan Tower Annex Hall"}})
    shorter = places["busan-tower"].model_copy(update={"place_id": "tower-short", "names": {"en": "Annex Hall"}})
    monkeypatch.setattr(chat_answer, "load_places", lambda: {"busan-tower-annex": longer, "tower-short": shorter})
    out = chat_answer.render_answer("[place:busan-tower-annex] is open.", "en", {"busan-tower-annex"})
    assert out == "Busan Tower Annex Hall is open."


# ---- build_sources ----


def out(name: str, data, **args) -> ToolOutput:
    return ToolOutput(name, args, data)


def place_dict(place_id: str) -> dict:
    return load_places()[place_id].model_dump()


def test_build_sources_without_tool_results_is_empty():
    assert chat_answer.build_sources([], {"haeundae-beach"}, "en") == []


def test_build_sources_includes_only_referenced_search_results_once_in_order():
    outputs = [
        out("search_places", [place_dict("haeundae-beach"), place_dict("busan-tower"), place_dict("taejongdae")]),
        out("search_places", [place_dict("busan-tower")]),  # 같은 결과를 또 불러도 한 번만
    ]
    sources = chat_answer.build_sources(outputs, {"busan-tower", "haeundae-beach"}, "ja")
    assert [(s.tool, s.id) for s in sources] == [("search_places", "haeundae-beach"), ("search_places", "busan-tower")]
    assert sources[0].title == load_places()["haeundae-beach"].names["ja"]


def test_build_sources_for_each_lookup_tool_and_empty_results():
    outputs = [
        out("get_weather", {"date": "2026-11-21", "hourly": [{"time": "x", "pop": 10, "pty": 0}]}),
        out("get_weather", {"date": "2026-11-30", "hourly": []}),  # 예보 없음은 근거가 아니다
        out("get_crowd", {"place_id": "haeundae-beach", "date": "2026-11-21", "ratio": None, "source": "weekday_rule"}),
        out("get_hours", {"place_id": "busan-tower", "opens": None, "closes": None, "closed_weekdays": [], "closed_dates": []}),
        out("get_hours", {"place_id": "gamcheon-village", "opens": "09:00", "closes": "18:00", "closed_weekdays": [], "closed_dates": []}),
        out("get_travel_time", {"from_place_id": "busan-tower", "to_place_id": "haeundae-beach", "minutes": 40, "mode": "subway"}),
        out("get_events", {"date": "2026-11-21", "events": []}),
        out("get_events", {"date": "2026-11-28", "events": [{"name": "행사"}]}),
    ]
    sources = chat_answer.build_sources(outputs, set(), "en")
    assert [(s.tool, s.id) for s in sources] == [
        ("get_weather", "busan-2026-11-21"),
        ("get_crowd", "haeundae-beach"),
        ("get_hours", "gamcheon-village"),
        ("get_travel_time", "busan-tower>haeundae-beach"),
        ("get_events", "2026-11-28"),
    ]
    assert all(s.title.strip() for s in sources)


# ---- PlanCreator ----


def make_creator(candidates=FIVE) -> PlanCreator:
    creator = PlanCreator(Profile(language="en"), dt.date(2026, 11, 28), "plan-new")
    creator.allow_search_results([load_places()[p].model_dump() for p in candidates])
    return creator


def test_create_plan_uses_build_plan_and_the_issued_plan_id():
    creator = make_creator()
    result = creator.create_plan(place_ids=FIVE[:4], date=None, start=None)

    assert "error" not in result and result["plan_id"] == "plan-new" and result["date"] == "2026-11-28"
    assert creator.plan is not None and creator.notice is None
    assert [s["place_id"] for s in result["stops"]] == [s.place_id for s in creator.plan.stops]
    assert validate_plan(creator.plan) == []
    # 방문 순서·시각은 build_plan 이 정한 값이다. 입력 순서와 다를 수 있다
    assert {s.place_id for s in creator.plan.stops} == set(FIVE[:4])


@pytest.mark.parametrize("count", [1, 2, 6])
def test_create_plan_requires_three_to_five_places(count):
    creator = make_creator(candidates=list(load_places())[:8])
    result = creator.create_plan(place_ids=list(load_places())[:count], date=None, start=None)
    assert result["error"]["code"] == "bad_place_count" and creator.plan is None and creator.notice == "incomplete"


def test_create_plan_rejects_unknown_and_unsearched_places():
    creator = make_creator(candidates=FIVE[:3])
    assert creator.create_plan(place_ids=["no-such-place", *FIVE[:2]], date=None, start=None)["error"]["code"] == "unknown_place"
    assert creator.create_plan(place_ids=[*FIVE[:3], "taejongdae"], date=None, start=None)["error"]["code"] == "place_not_searched"
    assert creator.plan is None
    assert make_creator(candidates=[]).create_plan(place_ids=FIVE[:3], date=None, start=None)["error"]["code"] == "place_not_searched"


def test_create_plan_with_nothing_usable_asks_for_new_interests():
    creator = make_creator(candidates=[])
    creator.create_plan(place_ids=["no-such-place"], date=None, start=None)
    assert creator.notice == "no_valid_places"
    creator.create_plan(place_ids=[], date=None, start=None)
    assert creator.notice == "no_valid_places"


@pytest.mark.parametrize(
    "code, notice", [("no_valid_places", "no_valid_places"), ("invalid_date", "invalid_date"), ("invalid_start", "invalid_start"),
                     ("data_unavailable", "data_unavailable"), ("something_new", "incomplete")]
)
def test_build_errors_become_notices(monkeypatch, code, notice):
    def boom(*args, **kwargs):
        raise PlanBuildError(code, "x")

    monkeypatch.setattr(chat_tools, "build_plan", boom)
    creator = make_creator()
    result = creator.create_plan(place_ids=FIVE[:3], date=None, start=None)
    assert result["error"]["code"] == code and creator.plan is None and creator.notice == notice


def test_real_build_errors_from_build_plan():
    creator = make_creator()
    assert creator.create_plan(place_ids=FIVE[:3], date="not-a-date", start=None)["error"]["code"] == "invalid_date"
    assert creator.notice == "invalid_date"
    assert creator.create_plan(place_ids=FIVE[:3], date=None, start="25:99")["error"]["code"] == "invalid_start"
    assert creator.notice == "invalid_start"


def test_a_failed_retry_keeps_the_plan_made_earlier_and_success_clears_the_notice():
    creator = make_creator()
    creator.create_plan(place_ids=FIVE[:3], date=None, start=None)
    first = creator.plan
    creator.create_plan(place_ids=FIVE[:2], date=None, start=None)  # 실패
    assert creator.plan == first and creator.notice == "incomplete"
    creator.create_plan(place_ids=FIVE[:4], date=None, start=None)
    assert creator.notice is None and len(creator.plan.stops) == 4


def test_place_ids_in_ignores_errors_and_malformed_items():
    assert chat_tools.place_ids_in({"error": {"code": "x", "message": "y"}}) == []
    assert chat_tools.place_ids_in([{"place_id": "a"}, {"name": "x"}, "s", {"place_id": 3}]) == ["a"]


def test_tool_limit_is_five():
    assert MAX_TOOL_CALLS == 5
    assert json.dumps(sorted(t.tool_name for t in chat_tools.LOOKUP_TOOLS)) == json.dumps(
        ["get_crowd", "get_events", "get_hours", "get_travel_time", "get_weather", "search_places"]
    )
