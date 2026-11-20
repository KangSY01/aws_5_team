"""scripts/build_curation.py 테스트. 네트워크를 쓰지 않는다."""
import json

from scripts import build_curation as bc


def place(pid, category="park", indoor=False, names=None):
    return {"place_id": pid, "category": category, "indoor": indoor, "names": names or {"en": pid}}


def pair(a, b, minutes):
    return {"from_place_id": a, "to_place_id": b, "minutes": minutes}


def test_place_tags_category와_TourAPI_분류와_indoor():
    assert bc.place_tags(place("a", "beach"), []) == ["sea", "nature"]
    assert bc.place_tags(place("a", "market", indoor=True), ["SH", "SH06"]) == ["food", "shopping", "indoor"]
    assert bc.place_tags(place("a", "observatory", indoor=True), ["HS", "HS02"]) == ["history", "night_view", "indoor"]
    assert bc.place_tags(place("a", "attraction"), ["VE", "VE01"]) == ["night_view"]
    assert bc.place_tags(place("a", "attraction"), ["EX", "EX07"]) == []  # 표에 없는 분류
    assert bc.place_tags(place("a", "no-such-category"), []) == []
    all_tags = {t for tags in (*bc.CATEGORY_TAGS.values(), *bc.LCLS_TAGS.values()) for t in tags}
    assert all_tags | {"indoor"} == set(bc.TAGS)  # 표에 TAGS 밖의 값이 없고, 모든 태그가 쓰인다


def test_foreigner_friendly_는_영어_일본어_중국어_중_이름이_있는_언어_수():
    assert bc.foreigner_friendly({}) == 0
    assert bc.foreigner_friendly({"en": "A"}) == 1
    assert bc.foreigner_friendly({"zh-Hans": "甲", "zh-Hant": "甲"}) == 1  # 중국어는 간체·번체를 합쳐 1
    assert bc.foreigner_friendly({"en": "A", "ja": "あ", "zh-Hant": "甲"}) == 3


def test_대체_후보는_30분_이내_가까운_순_최대_3곳():
    places = [place("beach", "beach"), place("p1"), place("p2"), place("p3"), place("p4"), place("far"),
              place("mall", "shopping", indoor=True), place("museum", "museum", indoor=True),
              place("far-museum", "museum", indoor=True)]
    pairs = [pair("beach", "p1", 12), pair("beach", "p2", 5), pair("beach", "p3", 30), pair("beach", "p4", 12),
             pair("beach", "far", 31), pair("beach", "mall", 3), pair("museum", "beach", 20),
             pair("beach", "far-museum", 45)]
    result = bc.build_curation(places, pairs, {}, {})
    beach = result["beach"]
    # nature 가 겹치는 공원만(쇼핑몰은 더 가깝지만 태그가 다르다). 같은 12분은 place_id 순, 30분은 포함, 31분은 제외
    assert beach["crowd_alternatives"] == ["p2", "p1", "p4"]
    assert beach["rain_alternatives"] == ["mall", "museum"]  # 실내만, 45분은 제외
    assert beach["source"] == "rule" and list(beach) == [*bc.FIELDS, "source"]
    assert result["museum"]["crowd_alternatives"] == []  # 쌍이 없는 곳(far-museum)은 넣지 않는다
    assert result["mall"]["rain_alternatives"] == []  # 자기 자신은 넣지 않는다
    assert result["p1"]["crowd_alternatives"] == ["beach"]


def test_crowd_alternatives_는_indoor_만_겹치면_넣지_않는다():
    places = [place("market", "market", indoor=True), place("tower", "observatory", indoor=True),
              place("mall", "shopping", indoor=True)]
    pairs = [pair("market", "tower", 5), pair("market", "mall", 20), pair("tower", "mall", 20)]
    result = bc.build_curation(places, pairs, {}, {})
    assert result["market"]["crowd_alternatives"] == ["mall"]  # shopping 이 겹친다. tower 는 indoor 만 겹친다
    assert result["tower"]["crowd_alternatives"] == []
    assert result["market"]["rain_alternatives"] == ["tower", "mall"]  # 비 대체 후보는 실내면 된다


def test_overrides_는_적은_필드만_덮어쓰고_source_가_manual():
    places = [place("a", "beach"), place("b", "beach")]
    overrides = {"a": {"tags": ["sea", "night_view"], "unknown_field": 1}, "no-such-place": {"tags": ["food"]}}
    result = bc.build_curation(places, [pair("a", "b", 10)], {}, overrides)
    assert result["a"] == {"tags": ["sea", "night_view"], "foreigner_friendly": 1, "crowd_alternatives": ["b"],
                           "rain_alternatives": [], "source": "manual"}
    assert result["b"]["source"] == "rule" and set(result) == {"a", "b"}


def test_curation_json은_규칙으로_다시_만든_값과_같다():
    """다르면 `uv run python -m scripts.build_curation` 을 다시 실행한다."""
    saved_text = bc.OUT_PATH.read_text(encoding="utf-8")
    places, pairs, lcls, overrides = bc.load_inputs()
    assert saved_text == bc.dump_curation(bc.build_curation(places, pairs, lcls, overrides))
    saved = json.loads(saved_text)
    known = {p["place_id"] for p in places}
    assert set(saved) == known
    for pid, entry in saved.items():
        assert set(entry["tags"]) <= set(bc.TAGS) and 0 <= entry["foreigner_friendly"] <= 3
        for field in ("crowd_alternatives", "rain_alternatives"):
            assert len(entry[field]) <= bc.MAX_ALTERNATIVES and pid not in entry[field] and set(entry[field]) <= known
    assert all(lcls.values())  # 모든 장소의 TourAPI 분류를 raw 에서 읽었다
    assert json.loads(bc.OVERRIDES_PATH.read_text(encoding="utf-8")) == {}  # 지금은 사람이 고친 항목이 없다


def test_curation_실제_데이터_예시():
    saved = json.loads(bc.OUT_PATH.read_text(encoding="utf-8"))
    assert saved["haeundae-beach"]["tags"] == ["sea", "nature"]
    assert saved["haeundae-beach"]["rain_alternatives"][0] == "sea-life-busan"
    assert saved["gamcheon-village"]["tags"] == ["culture"] and saved["gamcheon-village"]["foreigner_friendly"] == 3
