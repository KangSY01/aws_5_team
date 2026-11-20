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


# D 가 검수한 문장 (원문 그대로). 바뀌지 않아야 하는 기존 문장도 함께 고정한다
REVIEWED = {
    ("plan_invalid", "en"): "I couldn't save that because the schedule would not work (for example, stops would overlap). Nothing was changed.",
    ("plan_invalid", "ja"): "時間が重なるなどスケジュールが成り立たないため、保存できませんでした。何も変更していません。",
    ("plan_invalid", "zh-Hans"): "该安排无法成立（例如时间重叠），因此未保存，没有任何更改。",
    ("plan_invalid", "zh-Hant"): "該安排無法成立（例如時間重疊），因此未儲存，沒有任何變更。",
    ("plan_changed", "en"): "I updated {count} stop(s) in your itinerary. Locked stops were not changed.",
    ("plan_changed", "ja"): "旅程の{count}か所を更新しました。固定された訪問先は変更していません。",
    ("plan_changed", "zh-Hans"): "已更新行程中的 {count} 个地点。固定地点未更改。",
    ("plan_changed", "zh-Hant"): "已更新行程中的 {count} 個地點。固定地點未更改。",
    ("plan_created", "en"): "I made a {count}-stop plan for {date}: {places}.",
    ("plan_created", "ja"): "{date}の旅程（{count}か所）を作りました：{places}。",
    ("plan_created", "zh-Hans"): "已为 {date} 安排了 {count} 个地点的行程：{places}。",
    ("plan_created", "zh-Hant"): "已為 {date} 安排了 {count} 個地點的行程：{places}。",
    ("no_valid_places", "en"): "I couldn't find suitable places to build an itinerary. Tell me what you enjoy (for example food, the sea or culture) and I'll try again.",
    ("no_valid_places", "ja"): "旅程に合う場所が見つかりませんでした。興味のあること（グルメ、海、文化など）を教えてください。もう一度探します。",
    ("no_valid_places", "zh-Hans"): "没有找到适合安排行程的地点。请告诉我您的兴趣（例如美食、海边或文化），我会再试一次。",
    ("no_valid_places", "zh-Hant"): "沒有找到適合安排行程的地點。請告訴我您的興趣（例如美食、海邊或文化），我會再試一次。",
}


@pytest.mark.parametrize("key, language", sorted(REVIEWED))
def test_reviewed_messages_match_exactly(key, language):
    assert MESSAGES[key][language] == REVIEWED[(key, language)]


def test_plan_changed_formats_count_in_every_language():
    assert message("plan_changed", "ja", count=2) == "旅程の2か所を更新しました。固定された訪問先は変更していません。"
    assert message("plan_changed", "zh-Hans", count=2) == "已更新行程中的 2 个地点。固定地点未更改。"
    assert message("plan_changed", "zh-Hant", count=2) == "已更新行程中的 2 個地點。固定地點未更改。"
    assert message("plan_changed", "en", count=2) == "I updated 2 stop(s) in your itinerary. Locked stops were not changed."


# ---- 장소 이름 ----


def test_place_name_falls_back_to_other_languages():
    places = load_places()
    assert place_name(places["haeundae-beach"], "ja") == places["haeundae-beach"].names["ja"]
    # 일본어 이름이 없는 장소를 places.json 에서 찾는다 (ID 는 고정하지 않는다. place_id 순으로 첫 장소)
    partial = next((p for p in sorted(places.values(), key=lambda p: p.place_id) if not p.names.get("ja")), None)
    if partial is None:  # 이름 보충으로 모든 장소에 ja 가 생겼으면 the-bay-101 에서 ja 를 뺀 사본으로 검사한다
        base = places["the-bay-101"]
        partial = base.model_copy(update={"names": {k: v for k, v in base.names.items() if k != "ja"}})
    # 대체 순서는 표시 언어(ja) → en → ja → zh-Hans → zh-Hant → place_id 다. ja 가 없으니 en 부터 본다
    expected = next((partial.names[k] for k in ("en", "zh-Hans", "zh-Hant") if partial.names.get(k)), partial.place_id)
    assert place_name(partial, "ja") == expected
    # 실제 데이터가 한 언어만 갖고 있어도 en → zh-Hans → zh-Hant 순서가 지켜지는지 확인한다
    ordered = partial.model_copy(update={"names": {"zh-Hant": "繁", "zh-Hans": "简", "en": "English"}})
    assert place_name(ordered, "ja") == "English"
    assert place_name(ordered.model_copy(update={"names": {"zh-Hant": "繁", "zh-Hans": "简"}}), "ja") == "简"
    nameless = partial.model_copy(update={"names": {}})
    assert place_name(nameless, "en") == partial.place_id


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
        ["get_crowd", "get_events", "get_hours", "get_place_info", "get_restaurants", "get_return_options",
         "get_transit_info", "get_travel_time", "get_weather", "search_places"]
    )


def test_grounded_place_ids_collects_ids_from_every_tool_result():
    outputs = [
        out("search_places", [{"place_id": "busan-tower"}]),
        out("get_place_info", {
            "place_id": "gamcheon-village",
            "curation": {"crowd_alternatives": ["haeundae-beach", "no-such-place"], "rain_alternatives": None},
            "hours": {"opens": None, "raw_text": "원문"},
        }),
        out("get_events", {"date": "2026-11-28", "events": [{"name": "행사", "place_ids": ["jagalchi-market"]}]}),
        out("get_travel_time", {"from_place_id": "busan-tower", "to_place_id": "haeundae-beach", "minutes": 40}),
    ]
    assert chat_tools.grounded_place_ids(outputs) == {
        "busan-tower", "gamcheon-village", "haeundae-beach", "jagalchi-market",
    }
    assert chat_tools.grounded_place_ids([]) == set()


def test_build_sources_counts_raw_text_hours_and_place_info():
    outputs = [
        out("get_hours", {"place_id": "busan-tower", "opens": None, "closes": None, "closed_weekdays": [],
                          "closed_dates": [], "raw_text": "09:00~22:00"}),
        out("get_place_info", {"place_id": "gamcheon-village", "curation": None, "hours": {}}),
        out("get_place_info", {"place_id": "haeundae-beach", "curation": None, "hours": {}}),
    ]
    sources = chat_answer.build_sources(outputs, {"gamcheon-village"}, "en")
    assert [(s.tool, s.id) for s in sources] == [("get_hours", "busan-tower"), ("get_place_info", "gamcheon-village")]


# ---- 귀가 분산 (get_return_options, B) ----

RETURN_RESULT = {
    "date": "2026-11-28",
    "event": {"name": "해운대 빛축제", "start": "2026-11-28T18:00:00+09:00", "end": "2026-11-28T23:00:00+09:00",
              "main_place_id": "sea-life-busan"},
    "origin": {"place_id": "haeundae-beach", "station": "Haeundae"},
    "destination": {"station": "Seomyeon", "place_id": None, "is_default": True},
    "congested_station": {"station": "Haeundae", "main_place_id": "sea-life-busan"},
    "baseline": {"station": "Haeundae", "congested": True, "minutes": 39, "mode": "subway"},
    "options": [],
}


def test_main_place_id_counts_as_a_grounded_place():
    assert "main_place_id" in chat_tools.PLACE_ID_KEYS
    only_main = out("get_events", {"date": "2026-11-28", "events": [{"name": "x", "main_place_id": "sea-life-busan"}]})
    assert chat_tools.grounded_place_ids([only_main]) == {"sea-life-busan"}
    # destination.place_id 가 null 이어도 문제없고, 출발 장소와 대표 장소가 모두 근거가 된다
    assert chat_tools.grounded_place_ids([out("get_return_options", RETURN_RESULT)]) == {"haeundae-beach", "sea-life-busan"}


@pytest.mark.parametrize("language", LANGUAGES)
def test_return_options_become_a_source_with_the_route(language):
    sources = chat_answer.build_sources([out("get_return_options", RETURN_RESULT)], set(), language)

    assert [(s.tool, s.id) for s in sources] == [("get_return_options", "2026-11-28:Haeundae>Seomyeon")]
    assert sources[0].title == message("source_return", language, origin="Haeundae", destination="Seomyeon")
    assert "Haeundae" in sources[0].title and "Seomyeon" in sources[0].title


def test_return_options_without_a_route_are_not_a_source():
    broken = [
        out("get_return_options", {"error": {"code": "event_not_found", "message": "x"}}),
        out("get_return_options", {"date": "2026-11-28", "baseline": {}, "destination": {"station": "Seomyeon"}}),
        out("get_return_options", ["not", "a", "dict"]),
    ]
    assert chat_answer.build_sources(broken, set(), "en") == []


# ---- 지하철 정보·주변 음식점 (get_transit_info, get_restaurants, B 의 PR #55) ----
# 결과는 B 의 실제 도구로 만든다 (파일만 읽고 외부 API 를 부르지 않는다)

from app.tools.restaurants import get_restaurants  # noqa: E402
from app.tools.transit import get_transit_info  # noqa: E402


def test_transit_places_nested_in_from_and_to_are_grounded():
    data = get_transit_info(from_place_id="haeundae-beach", to_place_id="jagalchi-market")
    assert data["from"]["place_id"] == "haeundae-beach"  # 장소 ID 가 from·to 안에 중첩되어 있다
    assert chat_tools.grounded_place_ids([out("get_transit_info", data)]) == {"haeundae-beach", "jagalchi-market"}
    to_station = get_transit_info(from_place_id="haeundae-beach", to_station="Seomyeon")  # 도착이 역이면 place_id 가 null
    assert chat_tools.grounded_place_ids([out("get_transit_info", to_station)]) == {"haeundae-beach"}


def test_restaurant_ids_are_not_place_ids():
    data = get_restaurants(place_id="haeundae-beach", limit=3)
    assert data["restaurants"] and all(r["restaurant_id"].startswith("kto-") for r in data["restaurants"])
    assert "restaurant_id" not in chat_tools.PLACE_ID_KEYS
    assert chat_tools.grounded_place_ids([out("get_restaurants", data)]) == {"haeundae-beach"}  # 검색 기준 장소만
    by_station = get_restaurants(station="Seomyeon", limit=3)
    assert chat_tools.grounded_place_ids([out("get_restaurants", by_station)]) == set()


@pytest.mark.parametrize("language", LANGUAGES)
def test_transit_info_becomes_a_source_with_the_stations(language):
    data = get_transit_info(from_place_id="haeundae-beach", to_place_id="jagalchi-market")

    sources = chat_answer.build_sources([out("get_transit_info", data)], set(), language)

    assert [(s.tool, s.id) for s in sources] == [("get_transit_info", "Haeundae>Jagalchi")]
    assert sources[0].title == message("source_transit", language, origin="Haeundae", destination="Jagalchi")


@pytest.mark.parametrize("language", LANGUAGES)
def test_restaurants_become_a_source_named_after_the_area(language):
    by_place = get_restaurants(place_id="haeundae-beach", limit=2)
    by_station = get_restaurants(station="Seomyeon", limit=2)

    sources = chat_answer.build_sources([out("get_restaurants", by_place), out("get_restaurants", by_station)], set(), language)

    area = place_name(load_places()["haeundae-beach"], language)
    assert [(s.tool, s.id, s.title) for s in sources] == [
        ("get_restaurants", "haeundae-beach", message("source_restaurants", language, area=area)),
        ("get_restaurants", "station:Seomyeon", message("source_restaurants", language, area="Seomyeon")),
    ]
    assert "TourAPI" in sources[0].title  # 공공데이터 출처를 표기한다 (data-rules.md)


def test_transit_and_restaurant_results_without_data_are_not_sources():
    empty = get_restaurants(place_id="haeundae-beach", radius_m=1)  # 반경 안에 음식점이 없다
    assert empty["restaurants"] == []
    broken = [
        out("get_transit_info", get_transit_info(from_place_id="haeundae-beach", to_place_id="haeundae-beach")),  # same_place
        out("get_transit_info", {"from": {"station": "Haeundae"}, "to": None}),
        out("get_restaurants", get_restaurants(place_id="busan-tower")),  # restaurants_not_collected
        out("get_restaurants", empty),
        out("get_restaurants", ["not", "a", "dict"]),
    ]
    assert chat_answer.build_sources(broken, set(), "en") == []
