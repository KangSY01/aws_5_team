"""scripts/fetch_hours.py 테스트. 네트워크를 쓰지 않는다."""
import json

import pytest

from scripts import fetch_hours as fh
from scripts import fetch_places as fp


@pytest.mark.parametrize("text, expected", [
    ("05:00~22:00", ("05:00", "22:00")),
    ("9:00 ~ 18:00", ("09:00", "18:00")),
    ("09:00~20:00※ 점포 별로 상이함", ("09:00", "20:00")),
    ("10:00~22:00 (발권 마감 21:30)", ("10:00", "22:00")),  # 마감 안내는 빼고 본다
    ("09:00~18:00 (입장 마감 17:00)", ("09:00", "18:00")),
    # 아래는 한 구간으로 쓸 수 없다 → 모르는 값
    ("상시 개방", (None, None)),
    ("", (None, None)),
    ("08:00~24:00※ 자세한 사항은 전화 문의 바람", (None, None)),  # 24:00 은 시각으로 쓸 수 없다
    ("매년 6월~9월 09:00~18:00 ※ 자세한 사항은 홈페이지 참조", (None, None)),  # 기간 조건
    ("[하절기(3월~10월)]04:00~24:00[동절기(11월~2월)]05:00~24:00", (None, None)),
    ("- 평일 10:00~20:00- 주말 10:00~21:00", (None, None)),
    ("평일 10:00~20:00", (None, None)),  # 구간은 하나지만 요일 조건이 있다
    ("10:00~19:00 (입장 마감 18:00) 10:00~20:00 (입장 마감 19:00)", (None, None)),
    ("22:00~02:00", (None, None)),  # 자정을 넘는 구간
    ("10:00부터", (None, None)),
])
def test_parse_open_close_단순한_한_구간만_읽는다(text, expected):
    assert fh.parse_open_close(text) == expected


@pytest.mark.parametrize("text, expected", [
    ("매주 월요일 (단, 월요일이 공휴일인 경우 그 다음날을 휴관일로 함) / 1월 1일", [0]),
    ("매주 일요일", [6]),
    ("매주 일요일※ 점포 별로 상이함", []),  # 단서가 붙은 휴무는 넣지 않는다
    ("매주 화요일 (일부 매장 휴무)", []),
    ("매주 수요일 ※ 매장마다 다름", []),
    ("매주 월요일, 매주 화요일", [0, 1]),
    ("연중무휴", []),
    ("매월 첫째, 셋째, 다섯째 화요일", []),  # 매주가 아니다
    ("설·추석 당일", []),
    ("", []),
])
def test_parse_closed_weekdays_매주_요일만_읽는다(text, expected):
    assert fh.parse_closed_weekdays(text) == expected


def test_clean_text_태그와_엔티티를_정리한다():
    assert fh.clean_text("10:00~18:00<br />(입장 마감 17:30)<br>") == "10:00~18:00 / (입장 마감 17:30)"
    assert fh.clean_text("<b>연중무휴</b> &amp; 설날") == "연중무휴 & 설날"
    assert fh.clean_text(None) == ""


def test_build_entry_타입별_필드_이름():
    tourist = fh.build_entry("12", {"usetime": "04:30~20:30", "restdate": "연중무휴"})
    assert tourist == {"opens": "04:30", "closes": "20:30", "closed_weekdays": [], "closed_dates": [],
                       "raw_text": "이용시간: 04:30~20:30\n쉬는날: 연중무휴"}
    culture = fh.build_entry("14", {"usetimeculture": "09:00~18:00 (입장 마감 17:00)", "restdateculture": "매주 월요일"})
    assert (culture["opens"], culture["closes"], culture["closed_weekdays"]) == ("09:00", "18:00", [0])
    shopping = fh.build_entry("38", {"opentime": "09:00~22:00", "restdateshopping": ""})
    assert shopping["closes"] == "22:00" and shopping["raw_text"] == "이용시간: 09:00~22:00"
    # 다른 타입의 필드 이름으로 온 값이나 모르는 타입은 읽지 않는다
    assert fh.build_entry("12", {"usetimeculture": "09:00~18:00"}) == fh.UNKNOWN
    assert fh.build_entry("39", {"opentimefood": "09:00~18:00"}) == fh.UNKNOWN


def test_intro_item_단건과_빈_응답():
    wrap = lambda items: {"response": {"response": {"body": {"items": items}}}}  # noqa: E731
    assert fh.intro_item(wrap({"item": [{"usetime": "a"}]})) == {"usetime": "a"}
    assert fh.intro_item(wrap({"item": {"usetime": "a"}})) == {"usetime": "a"}
    assert fh.intro_item(wrap("")) == {} and fh.intro_item({}) == {}


def test_main_장소당_1회만_호출하고_저장된_응답은_다시_부르지_않는다(monkeypatch, tmp_path, capsys):
    places = [{"place_id": "a"}, {"place_id": "b"}, {"place_id": "busan-cinema-center"}]
    sources = {pid: {"contentids": {"ko": cid}, "kor_class": {"contenttypeid": "12"}}
               for pid, cid in (("a", "1"), ("b", "2"), ("busan-cinema-center", "3"))}
    (tmp_path / "places.json").write_text(json.dumps(places), encoding="utf-8")
    (tmp_path / "sources.json").write_text(json.dumps(sources), encoding="utf-8")
    for name, value in (("PLACES_PATH", tmp_path / "places.json"), ("SOURCES_PATH", tmp_path / "sources.json"),
                        ("RAW_DIR", tmp_path / "raw"), ("API_CALLS", 0),
                        ("OFFLINE", False), ("REUSE_RAW", False)):  # main 이 바꾸는 전역 값을 테스트 뒤에 되돌린다
        monkeypatch.setattr(fp, name, value)
    monkeypatch.setattr(fh, "OUT_PATH", tmp_path / "hours.json")
    monkeypatch.setattr(fh.config, "DATA_GO_KR_KEY", "SECRET")
    asked = []

    def fake_request(service, operation, extra):
        asked.append((service, operation, extra))
        fp.API_CALLS += 1
        text = "09:00~18:00" if extra["contentId"] == "1" else "상시 개방"
        return {"response": {"header": {"resultCode": "0000"},
                             "body": {"items": {"item": [{"usetime": text, "restdate": "매주 월요일"}]}}}}

    monkeypatch.setattr(fp, "request_json", fake_request)
    assert fh.main([]) == 0
    assert asked == [("KorService2", "detailIntro2", {"contentId": cid, "contentTypeId": "12"}) for cid in ("1", "2")]
    saved = json.loads((tmp_path / "hours.json").read_text(encoding="utf-8"))
    assert saved["hours"]["a"]["opens"] == "09:00" and saved["hours"]["a"]["closed_weekdays"] == [0]
    assert saved["hours"]["b"]["opens"] is None and saved["hours"]["b"]["raw_text"].startswith("이용시간: 상시 개방")
    assert saved["hours"]["busan-cinema-center"] == fh.UNKNOWN  # 국문 항목이 그 장소가 아니라 호출하지 않는다
    assert "SECRET" not in (tmp_path / "raw" / "a" / "ko_intro.json").read_text(encoding="utf-8")

    monkeypatch.setattr(fp, "request_json", lambda *a: pytest.fail("저장된 응답이 있으면 다시 부르지 않는다"))
    monkeypatch.setattr(fp, "API_CALLS", 0)
    assert fh.main([]) == 0 and fh.main(["--offline"]) == 0
    assert json.loads((tmp_path / "hours.json").read_text(encoding="utf-8")) == saved
    assert "API 호출 0회" in capsys.readouterr().out


def test_hours_json은_모든_장소가_있고_raw_text_에서_다시_읽은_값과_같다():
    """규칙을 바꿨으면 `uv run python -m scripts.fetch_hours --offline` 을 다시 실행한다.

    raw 응답은 git 에 없으므로, 파일에 남긴 원문(raw_text)에 같은 규칙을 다시 적용해 비교한다.
    """
    saved = json.loads(fh.OUT_PATH.read_text(encoding="utf-8"))
    assert list(saved["hours"]) == [p["place_id"] for p in fp.load_json(fp.PLACES_PATH, [])]
    assert saved["source"]["fields"] == {type_id: list(fields) for type_id, fields in fh.INTRO_FIELDS.items()}
    for pid, entry in saved["hours"].items():
        assert set(entry) == set(fh.UNKNOWN), pid
        lines = dict(line.split(": ", 1) for line in (entry["raw_text"] or "").splitlines())
        assert set(lines) <= {"이용시간", "쉬는날"}, pid
        assert (entry["opens"], entry["closes"]) == fh.parse_open_close(lines.get("이용시간", "")), pid
        assert entry["closed_weekdays"] == fh.parse_closed_weekdays(lines.get("쉬는날", "")), pid
        assert entry["closed_dates"] == [], pid
    assert saved["hours"]["busan-cinema-center"] == fh.UNKNOWN
