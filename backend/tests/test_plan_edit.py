"""plan_edit 부분 수정 도구 (작업 3). 조회 도구 없이 places.json·sample_plan.json 만 쓰므로 AWS 와 네트워크가 필요 없다."""

import json
import random
from pathlib import Path

import pytest

from app.models.plan import Plan, StopChange
from app.tools.plan_edit import PlanEditor, load_known_place_ids

DATA = Path(__file__).parents[1] / "app" / "data"
PLACES = json.loads((DATA / "places.json").read_text(encoding="utf-8"))
KNOWN = load_known_place_ids()
INDOOR = "shinsegae-centum-city"  # places.json 에 있는 장소

# sample_plan: s1 감천(10:00-11:30), s2 자갈치(12:00-13:00, locked), s3 부산타워(13:30-14:30), s4 해운대(15:30-17:00)
T = "2026-11-21T{}:00+09:00"


def load_plan() -> Plan:
    return Plan.model_validate_json((DATA / "sample_plan.json").read_text(encoding="utf-8"))


@pytest.fixture
def plan() -> Plan:
    return load_plan()


@pytest.fixture
def editor(plan) -> PlanEditor:
    editor = PlanEditor(plan)
    editor.allow_places([INDOOR, "gwangalli-beach"])  # search_places 가 돌려준 것으로 간주
    return editor


def stop_of(editor: PlanEditor, stop_id: str):
    return next(s for s in editor.current_plan.stops if s.stop_id == stop_id)


def error_code(result: dict) -> str:
    assert set(result) == {"error"}
    return result["error"]["code"]


def test_known_place_ids_come_from_places_json(plan):
    assert "haeundae-beach" in KNOWN and INDOOR in KNOWN
    assert {s.place_id for s in plan.stops} <= KNOWN


def test_tools_are_exposed_with_llm_visible_arguments_only(editor):
    names = {t.tool_name: set(t.tool_spec["inputSchema"]["json"]["properties"]) for t in editor.tools}
    assert names == {
        "replace_stop": {"stop_id", "new_place_id"},
        "add_stop": {"place_id", "start", "end"},
        "remove_stop": {"stop_id"},
        "move_stop": {"stop_id", "start", "end"},
    }
    assert all(t.tool_spec["description"] for t in editor.tools)


# ---- replace_stop ----


def test_replace_stop_changes_place_and_keeps_time(editor):
    before = stop_of(editor, "s4")
    result = editor.replace_stop(stop_id="s4", new_place_id=INDOOR)

    change = StopChange.model_validate(result)
    assert change.before == before
    assert change.after.place_id == INDOOR
    assert (change.after.start, change.after.end) == (before.start, before.end)
    assert stop_of(editor, "s4") == change.after


def test_replace_stop_rejects_locked_stop(editor, plan):
    result = editor.replace_stop(stop_id="s2", new_place_id=INDOOR)
    assert error_code(result) == "stop_locked"
    assert "unlock" in result["error"]["message"]
    assert editor.current_plan == plan


def test_replace_stop_rejects_unknown_stop(editor, plan):
    assert error_code(editor.replace_stop(stop_id="s99", new_place_id=INDOOR)) == "stop_not_found"
    assert editor.current_plan == plan


def test_replace_stop_rejects_place_not_in_places_json_even_if_searched(plan):
    editor = PlanEditor(plan)
    editor.allow_places(["no-such-place"])
    assert error_code(editor.replace_stop(stop_id="s4", new_place_id="no-such-place")) == "unknown_place"
    assert editor.current_plan == plan


def test_replace_stop_rejects_place_that_was_not_searched(plan):
    editor = PlanEditor(plan)  # 후보를 등록하지 않았다
    assert "taejongdae" in KNOWN
    assert error_code(editor.replace_stop(stop_id="s4", new_place_id="taejongdae")) == "place_not_searched"
    assert editor.current_plan == plan


def test_replace_stop_rejects_same_place(editor):
    editor.allow_places(["haeundae-beach"])
    assert error_code(editor.replace_stop(stop_id="s4", new_place_id="haeundae-beach")) == "no_change"


# ---- add_stop ----


def test_add_stop_assigns_new_id_and_keeps_time_order(editor):
    result = editor.add_stop(place_id=INDOOR, start=T.format("14:40"), end=T.format("15:20"))

    change = StopChange.model_validate(result)
    assert change.before is None
    assert change.after.stop_id == "s5" and change.after.locked is False
    assert [s.stop_id for s in editor.current_plan.stops] == ["s1", "s2", "s3", "s5", "s4"]


def test_add_stop_rejects_bad_places(editor, plan):
    assert error_code(editor.add_stop(place_id="no-such-place", start=T.format("16:00"), end=T.format("17:00"))) == "unknown_place"
    assert error_code(editor.add_stop(place_id="taejongdae", start=T.format("16:00"), end=T.format("17:00"))) == "place_not_searched"
    assert editor.current_plan == plan


@pytest.mark.parametrize(
    "start, end",
    [
        ("2026-11-21T16:00:00", "2026-11-21T17:00:00"),  # 시간대 없음
        ("tomorrow", "2026-11-21T17:00:00+09:00"),
        (T.format("17:00"), T.format("16:00")),  # start 가 end 보다 늦음
        (T.format("16:00"), T.format("16:00")),
        (1763712000, T.format("17:00")),  # 숫자(타임스탬프)는 받지 않는다
    ],
)
def test_add_stop_rejects_invalid_times(editor, plan, start, end):
    assert error_code(editor.add_stop(place_id=INDOOR, start=start, end=end)) == "invalid_time"
    assert editor.current_plan == plan


# ---- remove_stop ----


def test_remove_stop(editor):
    before = stop_of(editor, "s3")
    change = StopChange.model_validate(editor.remove_stop(stop_id="s3"))
    assert change.before == before and change.after is None
    assert [s.stop_id for s in editor.current_plan.stops] == ["s1", "s2", "s4"]


def test_remove_stop_rejects_locked_and_unknown(editor, plan):
    assert error_code(editor.remove_stop(stop_id="s2")) == "stop_locked"
    assert error_code(editor.remove_stop(stop_id="s99")) == "stop_not_found"
    assert editor.current_plan == plan


# ---- move_stop ----


def test_move_stop_changes_time_and_keeps_place(editor):
    before = stop_of(editor, "s1")
    change = StopChange.model_validate(editor.move_stop(stop_id="s1", start=T.format("09:00"), end=T.format("10:30")))
    assert change.before == before
    assert change.after.place_id == before.place_id
    assert change.after.start.isoformat() == "2026-11-21T09:00:00+09:00"
    assert change.after.end.isoformat() == "2026-11-21T10:30:00+09:00"


def test_move_stop_keeps_time_order(editor):
    editor.move_stop(stop_id="s1", start=T.format("18:00"), end=T.format("19:00"))
    assert [s.stop_id for s in editor.current_plan.stops] == ["s2", "s3", "s4", "s1"]


def test_move_stop_rejections(editor, plan):
    assert error_code(editor.move_stop(stop_id="s2", start=T.format("09:00"), end=T.format("10:00"))) == "stop_locked"
    assert error_code(editor.move_stop(stop_id="s99", start=T.format("09:00"), end=T.format("10:00"))) == "stop_not_found"
    assert error_code(editor.move_stop(stop_id="s1", start=T.format("11:00"), end=T.format("10:00"))) == "invalid_time"
    assert error_code(editor.move_stop(stop_id="s1", start=T.format("10:00"), end=T.format("11:30"))) == "no_change"
    assert editor.current_plan == plan


# ---- 요청 범위 상태와 plan_changes ----


def test_caller_plan_is_not_mutated(plan):
    snapshot = plan.model_dump()
    editor = PlanEditor(plan)
    editor.allow_places([INDOOR])
    editor.replace_stop(stop_id="s4", new_place_id=INDOOR)
    editor.remove_stop(stop_id="s1")
    assert plan.model_dump() == snapshot


def test_editors_do_not_share_state(plan):
    first, second = PlanEditor(plan), PlanEditor(plan)
    first.allow_places([INDOOR])
    first.replace_stop(stop_id="s4", new_place_id=INDOOR)
    assert second.net_changes() == []
    assert error_code(second.replace_stop(stop_id="s4", new_place_id=INDOOR)) == "place_not_searched"


def test_net_changes_merges_repeated_edits(editor):
    original = stop_of(editor, "s4")
    editor.replace_stop(stop_id="s4", new_place_id=INDOOR)
    editor.replace_stop(stop_id="s4", new_place_id="gwangalli-beach")
    editor.move_stop(stop_id="s4", start=T.format("16:00"), end=T.format("17:30"))

    (change,) = editor.net_changes()
    assert change.before == original  # 처음 before
    assert change.after == stop_of(editor, "s4")  # 마지막 after
    assert change.after.place_id == "gwangalli-beach"


def test_net_changes_drops_edits_that_cancel_out(editor):
    editor.allow_places(["haeundae-beach"])
    editor.replace_stop(stop_id="s4", new_place_id=INDOOR)
    editor.replace_stop(stop_id="s4", new_place_id="haeundae-beach")  # 원래대로
    added = StopChange.model_validate(editor.add_stop(place_id=INDOOR, start=T.format("18:00"), end=T.format("19:00")))
    editor.remove_stop(stop_id=added.stop_id)  # 추가했다가 제거
    assert editor.net_changes() == []


def test_net_changes_reports_add_and_remove(editor):
    removed = stop_of(editor, "s3")
    editor.remove_stop(stop_id="s3")
    editor.add_stop(place_id=INDOOR, start=T.format("18:00"), end=T.format("19:00"))

    by_id = {c.stop_id: c for c in editor.net_changes()}
    assert by_id["s3"].before == removed and by_id["s3"].after is None
    assert by_id["s5"].before is None and by_id["s5"].after.place_id == INDOOR


def test_removed_stop_id_is_not_reused(editor):
    editor.remove_stop(stop_id="s4")
    change = StopChange.model_validate(editor.add_stop(place_id=INDOOR, start=T.format("18:00"), end=T.format("19:00")))
    assert change.after.stop_id == "s5"


def test_allow_search_results_reads_place_dicts_and_ignores_errors(plan):
    editor = PlanEditor(plan)
    editor.allow_search_results({"error": {"code": "api_error", "message": "x"}})  # 실패한 조회
    editor.allow_search_results([PLACES[1], {"name": "id 없음"}, "문자열", {"place_id": 3}])
    searched, not_searched = PLACES[1]["place_id"], PLACES[2]["place_id"]
    assert searched != plan.stops[3].place_id  # s4 의 현재 장소와 달라야 교체가 성립한다
    assert error_code(editor.replace_stop(stop_id="s4", new_place_id=not_searched)) == "place_not_searched"
    assert "error" not in editor.replace_stop(stop_id="s4", new_place_id=searched)


def test_known_place_ids_can_be_injected(plan):
    editor = PlanEditor(plan, known_place_ids={"only-this"})
    editor.allow_places([INDOOR, "only-this"])
    assert error_code(editor.replace_stop(stop_id="s4", new_place_id=INDOOR)) == "unknown_place"
    assert "error" not in editor.replace_stop(stop_id="s4", new_place_id="only-this")


# ---- 무작위 도구 호출에서도 지켜지는 규칙 ----

_TIMES = [T.format(h) for h in ("08:00", "09:30", "11:00", "13:00", "15:00", "17:00", "19:00")] + ["bad", "2026-11-21T10:00:00"]
_STOP_IDS = ["s1", "s2", "s3", "s4", "s5", "s6", "zz"]
_PLACE_IDS = sorted(KNOWN) + ["no-such-place"]


def _random_call(editor: PlanEditor, rng: random.Random) -> dict:
    match rng.choice(["replace", "add", "remove", "move", "search"]):
        case "replace":
            return editor.replace_stop(stop_id=rng.choice(_STOP_IDS), new_place_id=rng.choice(_PLACE_IDS))
        case "add":
            return editor.add_stop(place_id=rng.choice(_PLACE_IDS), start=rng.choice(_TIMES), end=rng.choice(_TIMES))
        case "remove":
            return editor.remove_stop(stop_id=rng.choice(_STOP_IDS))
        case "move":
            return editor.move_stop(stop_id=rng.choice(_STOP_IDS), start=rng.choice(_TIMES), end=rng.choice(_TIMES))
        case _:
            editor.allow_places(rng.sample(_PLACE_IDS, 3))
            return {}


@pytest.mark.parametrize("seed", range(150))
def test_random_edit_sequences_keep_rules(seed):
    rng = random.Random(seed)
    plan = load_plan()
    original = {s.stop_id: s for s in plan.stops}
    editor = PlanEditor(plan)

    for _ in range(rng.randint(1, 15)):
        snapshot = editor.current_plan
        result = _random_call(editor, rng)
        if "error" in result:  # 거부된 호출은 일정을 바꾸지 않는다
            assert editor.current_plan == snapshot

    current = {s.stop_id: s for s in editor.current_plan.stops}
    # locked Stop 은 어떤 호출 뒤에도 그대로다
    for stop_id, stop in original.items():
        if stop.locked:
            assert current[stop_id] == stop
    # 어떤 Stop 도 places.json 밖의 장소를 갖지 않고, 시각 구간이 뒤집히지 않는다
    assert all(s.place_id in KNOWN and s.start < s.end for s in current.values())
    assert [s.start for s in editor.current_plan.stops] == sorted(s.start for s in editor.current_plan.stops)
    # plan_changes: before 는 요청 시작 시점 값, 변경 목록을 원래 일정에 적용하면 현재 일정이 된다
    rebuilt = dict(original)
    for change in editor.net_changes():
        assert change.before == original.get(change.stop_id)
        assert change.before != change.after
        rebuilt.pop(change.stop_id, None)
        if change.after is not None:
            rebuilt[change.stop_id] = change.after
    assert rebuilt == current
    assert plan.model_dump() == load_plan().model_dump()  # 호출자의 일정은 그대로
