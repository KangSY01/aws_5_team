"""scripts/build_congestion.py 테스트. 네트워크를 쓰지 않는다. 원본(data/raw)은 git 에 없으므로 읽지 않는다."""
import datetime as dt
import json

import pytest

from scripts import build_congestion as bc
from scripts import fetch_places as fp


def row(name, ymd, rate, gu="26350"):
    return {"baseYmd": ymd, "areaCd": "26", "areaNm": "부산광역시", "signguCd": gu, "signguNm": "구",
            "tAtsNm": name, "cnctrRate": rate}


def test_build_congestion_이름이_정확히_같은_항목만_뽑는다():
    raw = {
        "26350": [row("해운대해수욕장", "20261129", "61.5"), row("해운대해수욕장", "20261128", "71.43"),
                  row("해운대 해수욕장", "20261128", "1"),  # 띄어쓰기가 다르면 다른 이름이다
                  row("해운대해수욕장 야외무대", "20261128", "2"),
                  row("더베이101", "20261128", "100.0")],
        "26110": [row("BIFF 광장", "20261128", "50"),  # 표에는 있지만 places 에 없는 장소
                  row("국제시장", "날짜아님", "50"), row("국제시장", "20261128", "숫자아님"),
                  row("국제시장", "20261128", "33")],
    }
    result = bc.build_congestion(raw, ["the-bay-101", "haeundae-beach", "gukje-market", "gamcheon-village"])
    assert result == {
        "the-bay-101": {"2026-11-28": 100.0},
        "haeundae-beach": {"2026-11-28": 71.43, "2026-11-29": 61.5},  # 날짜순
        "gukje-market": {"2026-11-28": 33.0},  # 읽을 수 없는 항목은 버린다
    }
    assert list(result) == ["the-bay-101", "haeundae-beach", "gukje-market"]  # places 순서, 값이 없는 장소는 뺀다


def test_build_congestion_같은_이름이_다른_값으로_두_번_나오면_멈춘다():
    raw = {"26110": [row("국제시장", "20261128", "33")], "26230": [row("국제시장", "20261128", "34", gu="26230")]}
    with pytest.raises(ValueError):
        bc.build_congestion(raw, ["gukje-market"])
    same = {"26110": [row("국제시장", "20261128", "33"), row("국제시장", "20261128", "33.0")]}
    assert bc.build_congestion(same, ["gukje-market"]) == {"gukje-market": {"2026-11-28": 33.0}}


def test_dump_congestion_은_장소_하나가_한_줄():
    text = bc.dump_congestion({"api": bc.API}, {"a": {"2026-11-28": 71.43}, "b": {"2026-11-28": 5.0}})
    assert json.loads(text) == {"meta": {"api": bc.API}, "places": {"a": {"2026-11-28": 71.43}, "b": {"2026-11-28": 5.0}}}
    assert '    "a": {"2026-11-28": 71.43},\n' in text and text.endswith("}\n")


def test_congestion_json은_매핑_표의_장소와_기간_안의_값만_있다():
    """원본이나 places.json 이 바뀌면 `uv run python -m scripts.build_congestion` 을 다시 실행한다."""
    data = json.loads(bc.OUT_PATH.read_text(encoding="utf-8"))
    place_ids = [p["place_id"] for p in fp.load_json(fp.PLACES_PATH, [])]
    meta, places = data["meta"], data["places"]
    assert meta["api"] == bc.API and meta["provider"]
    # 표에 있고 places.json 에 있는 장소가 모두 들어 있다 (places.json 순서)
    assert list(places) == [pid for pid in place_ids if pid in bc.PLACE_NAMES]
    assert meta["names"] == {pid: bc.PLACE_NAMES[pid] for pid in places}
    start, end = (dt.date.fromisoformat(meta["period"][key]) for key in ("start", "end"))
    for pid, days in places.items():
        assert days and list(days) == sorted(days), pid
        assert all(start <= dt.date.fromisoformat(day) <= end for day in days), pid
        assert all(isinstance(rate, (int, float)) and 0 <= rate <= 100 for rate in days.values()), pid
    assert "2026-11-28" in places["haeundae-beach"]  # 데모일


def test_PLACE_NAMES_는_이름이_겹치지_않는다():
    assert len(set(bc.PLACE_NAMES.values())) == len(bc.PLACE_NAMES)
