"""scripts/fetch_places.py 테스트. 네트워크를 쓰지 않는다."""
import pytest

from scripts import fetch_places as fp

HAEUNDAE = (35.1587, 129.1604)
STATIONS = [
    {"name": "Haeundae", "lat": 35.1640, "lng": 129.1587},
    {"name": "Jagalchi", "lat": 35.0966, "lng": 129.0306},
]


def cand(cid, title, lat=HAEUNDAE[0], lng=HAEUNDAE[1], addr="부산광역시 해운대구"):
    return {"contentid": cid, "title": title, "addr1": addr, "lat": lat, "lng": lng}


def test_parse_items_빈_응답과_단건():
    empty = {"response": {"header": {"resultCode": "0000"}, "body": {"items": ""}}}
    assert fp.parse_items(empty) == []
    one = {"response": {"header": {"resultCode": "0000"}, "body": {"items": {"item": {
        "contentid": "1", "title": "A", "addr1": "부산", "mapx": "129.1", "mapy": "35.1"}}}}}
    assert fp.parse_items(one)[0]["lat"] == 35.1


def test_parse_items_오류_코드는_예외():
    with pytest.raises(fp.FetchError):
        fp.parse_items({"response": {"header": {"resultCode": "0030", "resultMsg": "KEY"}}})


def test_pick_kor_규칙():
    seed = {"name_ko": "해운대 해수욕장"}
    assert fp.pick_kor(seed, [])[1] == "no_match"
    only = cand("1", "아무거나")
    assert fp.pick_kor(seed, [only])[0] == only
    exact = cand("2", "해운대해수욕장")
    assert fp.pick_kor(seed, [cand("3", "해운대시장"), exact])[0] == exact
    assert fp.pick_kor(seed, [cand("3", "가"), cand("4", "나")])[1] == "multiple_candidates"
    by_query = {"name_ko": "해운대전통시장", "query": "해운대시장"}  # 제목이 검색어와 같아도 고른다
    assert fp.pick_kor(by_query, [cand("5", "해운대시장"), cand("6", "해운대시장 먹자골목")])[0]["contentid"] == "5"
    pinned = {**seed, "contentid": "4"}
    assert fp.pick_kor(pinned, [cand("3", "가"), cand("4", "나")])[0]["contentid"] == "4"


@pytest.mark.parametrize("title, expected", [
    ("부산 감천문화마을", "감천문화마을"),  # 앞의 부산을 뺀다
    ("海云台海水浴场(해운대해수욕장)", "해운대해수욕장"),
    ("ヘリダンギル（해리단길）", "해리단길"),  # 전각 괄호
    ("海东龙宫寺(釜山)해동 용궁사(부산)", "해동용궁사부산"),  # 괄호 밖 한글도 뽑고, 중간의 "부산" 은 그대로
    ("The Bay 101 (더베이101)", "101더베이101"),  # 숫자도 뽑는다
    ("Busan Tower", ""),
    ("부산타워", "타워"),
])
def test_normalize_korean(title, expected):
    assert fp.normalize_korean(title) == expected


@pytest.mark.parametrize("title, expected", [
    ("海云台海水浴场(해운대해수욕장)", "海云台海水浴场"),
    ("ヘリダンギル（해리단길）", "ヘリダンギル"),  # 전각 괄호
    ("釜山札嘎其市场부산 자갈치시장", "釜山札嘎其市场"),  # 괄호 밖 한글
    ("海东龙宫寺(釜山)해동 용궁사(부산)", "海东龙宫寺(釜山)"),  # 한글 없는 괄호는 남긴다
    ("海東龍宮寺(釜山)(해동 용궁사(부산))", "海東龍宮寺(釜山)"),  # 중첩 괄호
    ("Haeundae Amso Galbijip ( 해운대암소갈비집)", "Haeundae Amso Galbijip"),
    ("Orchid (난초) Garden", "Orchid Garden"),
    ("  Busan Tower  ", "Busan Tower"),
    ("(해운대)", ""),
    ("해운대 (해운대)", ""),
])
def test_strip_korean(title, expected):
    assert fp.strip_korean(title) == expected


def test_match_kind_규칙():
    assert fp.match_kind("국제시장", "국제시장", 800) == "exact"  # exact 는 거리와 무관
    assert fp.match_kind("국제시장", "국제시장먹자골목", 23) == "contains"
    assert fp.match_kind("국제시장먹자골목", "국제시장", 23) == "contains"  # 반대 방향도
    assert fp.match_kind("국제시장", "국제시장먹자골목", 400) is None  # 300m 밖
    assert fp.match_kind("해운", "해운대해수욕장", 10) is None  # 짧은 쪽이 3글자 미만
    assert fp.match_kind("", "국제시장", 10) is None and fp.match_kind("국제시장", "", 10) is None
    assert fp.match_kind("해운대", "다른곳", 10) is None


def test_pick_foreign_거리가_가까워도_한국어가_다르면_고르지_않는다():
    kor = cand("1", "해운대해수욕장")
    wrong = cand("2", "Hyeongje Gukbap (형제국밥)", lat=HAEUNDAE[0] + 0.001)
    right = cand("3", "Haeundae Beach (해운대 해수욕장)", lat=HAEUNDAE[0] + 0.002)
    item, reason, near = fp.pick_foreign(kor, [wrong, right])
    assert (item["contentid"], item["name"], item["match"], reason) == ("3", "Haeundae Beach", "exact", "")
    assert [c["contentid"] for c in near] == ["2", "3"]  # 거리순


def test_pick_foreign_괄호_밖_한글과_부산_접두사():
    chs = cand("2", "釜山札嘎其市场부산 자갈치시장")
    item = fp.pick_foreign(cand("1", "자갈치시장"), [chs])[0]
    assert (item["name"], item["match"]) == ("釜山札嘎其市场", "exact")
    item = fp.pick_foreign(cand("1", "부산 감천문화마을"), [cand("3", "甘川文化村(감천문화마을)")])[0]
    assert item["name"] == "甘川文化村"


def test_pick_foreign_포함_일치는_exact보다_뒤():
    kor = cand("1", "국제시장")
    contains = cand("2", "国际市场美食街(국제시장 먹자골목)", lat=HAEUNDAE[0] + 0.001)  # 더 가까움
    exact = cand("3", "国际市场(국제시장)", lat=HAEUNDAE[0] + 0.002)
    assert fp.pick_foreign(kor, [contains, exact])[0]["contentid"] == "3"
    assert fp.pick_foreign(kor, [contains])[0]["match"] == "contains"


def test_pick_foreign_1000m_패스에서는_exact만_300m_밖이면_포함은_불가():
    kor = cand("1", "국제시장")
    far_contains = cand("2", "国际市场美食街(국제시장 먹자골목)", lat=HAEUNDAE[0] + 0.006)  # 약 670m
    far_exact = cand("3", "国际市场(국제시장)", lat=HAEUNDAE[0] + 0.006)
    assert fp.pick_foreign(kor, [far_contains], radius=1000)[1] == "no_korean_match"
    assert fp.pick_foreign(kor, [far_exact], radius=1000)[0]["contentid"] == "3"
    assert fp.pick_foreign(kor, [far_exact])[1] == "no_korean_match"  # 300m 패스에는 후보 자체가 없다


def test_pick_foreign_실패_사유():
    kor = cand("1", "해운대해수욕장")
    assert fp.pick_foreign(kor, [])[1] == "no_korean_match"
    assert fp.pick_foreign(kor, [cand("2", "Other (다른곳)")])[1] == "no_korean_match"
    assert fp.pick_foreign(kor, [cand("2", "Haeundae Beach")])[1] == "title_without_korean"  # 한글 없음
    assert fp.pick_foreign(kor, [cand("2", "Haeundae Beach"), cand("3", "Other (다른곳)")])[1] == "no_korean_match"
    only_korean = cand("4", "해운대해수욕장")  # 한국어를 빼면 이름이 빈다
    assert fp.pick_foreign(kor, [only_korean])[1] == "empty_name"
    named = cand("5", "Beach (해운대해수욕장)", lat=HAEUNDAE[0] + 0.002)
    assert fp.pick_foreign(kor, [only_korean, named])[0]["contentid"] == "5"  # 이름이 있는 일치를 쓴다


def test_pick_foreign_타입으로_거르지_않는다():
    kor = cand("1", "센텀시티")
    shop_en = {**cand("2", "Centum City Dept (센텀시티)"), "contenttypeid": "79"}  # 영문 쇼핑 번호
    assert fp.pick_foreign(kor, [shop_en])[0]["name"] == "Centum City Dept"


def test_find_foreign_name_300m_없으면_1000m로_한_번_더(monkeypatch, tmp_path):
    kor = cand("1", "해운대해수욕장")
    far = cand("9", "Haeundae Beach (해운대해수욕장)", lat=HAEUNDAE[0] + 0.006)  # 약 670m
    calls = []

    def fake_nearby(service, lat, lng, raw_path, radius=300):
        calls.append((radius, raw_path.name))
        return [far] if radius == 1000 else []

    monkeypatch.setattr(fp, "search_nearby", fake_nearby)
    item, reason, _, radius = fp.find_foreign_name("en", kor, tmp_path)
    assert (item["name"], reason, radius) == ("Haeundae Beach", "", 1000)
    assert calls == [(300, "en.json"), (1000, "en_r1000.json")]


def test_find_foreign_name_300m에서_찾으면_1000m는_부르지_않는다(monkeypatch, tmp_path):
    calls = []

    def fake_nearby(service, lat, lng, raw_path, radius=300):
        calls.append(radius)
        return [cand("2", "Haeundae Beach (해운대해수욕장)")]

    monkeypatch.setattr(fp, "search_nearby", fake_nearby)
    assert fp.find_foreign_name("en", cand("1", "해운대해수욕장"), tmp_path)[3] == 300
    assert calls == [300]


def test_find_foreign_name_둘_다_없으면_no_korean_match(monkeypatch, tmp_path):
    monkeypatch.setattr(fp, "search_nearby", lambda *a, **k: [cand("2", "Other (다른곳)")])
    item, reason, near, radius = fp.find_foreign_name("ja", cand("1", "해운대해수욕장"), tmp_path)
    assert (item, reason, radius) == (None, "no_korean_match", 1000)
    assert near[0]["title"] == "Other (다른곳)"


class _Resp:
    def __init__(self, body: bytes):
        self._body = body

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _http_error(code):
    import urllib.error
    return urllib.error.HTTPError("http://x", code, "err", {}, None)


def test_request_json_500은_1회_재시도(monkeypatch):
    calls = []

    def fake_urlopen(url, timeout):
        calls.append(timeout)
        if len(calls) == 1:
            raise _http_error(500)
        return _Resp(b'{"response": {}}')

    monkeypatch.setattr(fp.urllib.request, "urlopen", fake_urlopen)
    assert fp.request_json("EngService2", "locationBasedList2", {}) == {"response": {}}
    assert calls == [5, 5]


def test_request_json_계속_500이면_실패_키는_메시지에_없다(monkeypatch):
    monkeypatch.setattr(fp.config, "DATA_GO_KR_KEY", "SECRET")
    calls = []

    def always_500(url, timeout):
        calls.append(1)
        raise _http_error(500)

    monkeypatch.setattr(fp.urllib.request, "urlopen", always_500)
    with pytest.raises(fp.FetchError) as e:
        fp.request_json("EngService2", "locationBasedList2", {})
    assert len(calls) == 2
    assert "HTTP 500" in str(e.value) and "SECRET" not in str(e.value)


def test_request_json_4xx는_재시도하지_않는다(monkeypatch):
    calls = []

    def forbidden(url, timeout):
        calls.append(1)
        raise _http_error(403)

    monkeypatch.setattr(fp.urllib.request, "urlopen", forbidden)
    with pytest.raises(fp.FetchError):
        fp.request_json("KorService2", "searchKeyword2", {})
    assert len(calls) == 1


def test_search_nearby_파라미터와_raw_저장(monkeypatch, tmp_path):
    seen = {}

    def fake_request(service, operation, extra):
        seen.update(service=service, operation=operation, extra=extra)
        return {"response": {"header": {"resultCode": "0000"}, "body": {"items": ""}}}

    monkeypatch.setattr(fp, "request_json", fake_request)
    monkeypatch.setattr(fp.config, "DATA_GO_KR_KEY", "SECRET")
    raw = tmp_path / "p" / "en.json"
    assert fp.search_nearby("EngService2", 35.1, 129.1, raw) == []
    assert seen["operation"] == "locationBasedList2"
    assert seen["extra"] == {"mapX": 129.1, "mapY": 35.1, "radius": 300, "arrange": "E"}
    fp.search_nearby("EngService2", 35.1, 129.1, raw, radius=1000)
    assert seen["extra"]["radius"] == 1000
    assert "SECRET" not in raw.read_text(encoding="utf-8")


def test_nearest_station_거리_상한():
    assert fp.nearest_station(*HAEUNDAE, STATIONS) == "Haeundae"
    assert fp.nearest_station(35.053, 129.085, STATIONS) is None  # 3km 초과


def test_build_place_성공과_review(monkeypatch):
    asked = []

    def fake_nearby(service, lat, lng, raw_path, radius=300):
        asked.append(service)
        if service == "EngService2":
            return [cand("10", "Haeundae Beach (해운대해수욕장)")]
        if service == "JpnService2":
            return [cand("13", "海雲台海水浴場")]  # 괄호 없음: 비교 불가
        if service == "ChsService2":
            raise fp.FetchError("HTTP 500")  # 이 언어만 실패
        return [cand("11", "海雲臺(다른곳)", lat=HAEUNDAE[0] + 0.001),
                cand("12", "海雲臺海水浴場(해운대해수욕장)", lat=HAEUNDAE[0] + 0.002)]  # 일치하는 쪽 선택

    monkeypatch.setattr(fp, "search_keyword", lambda q, p: [cand("1", "해운대해수욕장")])
    monkeypatch.setattr(fp, "search_nearby", fake_nearby)
    seed = {"place_id": "haeundae-beach", "name_ko": "해운대해수욕장", "query": "해운대",
            "category": "beach", "indoor": False}
    existing = {"place_id": "haeundae-beach", "names": {"en": "x", "ja": "海雲台海水浴場",
                "zh-Hans": "海云台海水浴场", "zh-Hant": "海雲臺海水浴場"},
                "lat": 1.0, "lng": 1.0, "category": "beach", "indoor": False, "nearest_station": None}
    reviews: list[dict] = []
    place, source = fp.build_place(seed, existing, STATIONS, reviews)
    assert place["names"]["en"] == "Haeundae Beach"
    assert place["names"]["ja"] == "海雲台海水浴場"  # 실패한 언어는 기존 값 유지
    assert place["nearest_station"] == "Haeundae"
    assert place["names"]["zh-Hant"] == "海雲臺海水浴場"  # 더 가까운 다른 곳이 아니라 한국어가 일치하는 항목
    assert {r["lang"]: r["reason"] for r in reviews} == {
        "ja": "title_without_korean", "zh-Hans": "api_error: HTTP 500"}
    assert source["contentids"] == {"ko": "1", "en": "10", "zh-Hant": "12"}
    assert source["match_radius_m"] == {"en": 300, "zh-Hant": 300}


def test_build_place_시드_names가_API보다_우선하고_그_언어는_호출하지_않는다(monkeypatch):
    asked = []

    def fake_nearby(service, lat, lng, raw_path, radius=300):
        asked.append(service)
        return [cand("10", "Haeundae Beach (해운대해수욕장)")]

    monkeypatch.setattr(fp, "search_keyword", lambda q, p: [cand("1", "해운대해수욕장")])
    monkeypatch.setattr(fp, "search_nearby", fake_nearby)
    seed = {"place_id": "haeundae-beach", "name_ko": "해운대해수욕장", "query": "해운대",
            "category": "beach", "indoor": False,
            "names": {"en": "Haeundae Sea (직접)", "ja": "海雲台", "zh-Hans": "海云台", "zh-Hant": "海雲臺"}}
    reviews: list[dict] = []
    place, source = fp.build_place(seed, None, STATIONS, reviews)
    assert place["names"] == seed["names"]  # 괄호를 떼지 않고 그대로
    assert asked == [] and reviews == []
    assert source["names_overridden"] == ["en", "ja", "zh-Hans", "zh-Hant"]


def test_build_place_신규_장소는_이름이_1개만_있어도_쓰고_빠진_언어는_review(monkeypatch):
    def fake_nearby(service, lat, lng, raw_path, radius=300):
        return [cand("10", "Haeundae Beach (해운대해수욕장)")] if service == "EngService2" else []

    monkeypatch.setattr(fp, "search_keyword", lambda q, p: [cand("1", "해운대해수욕장")])
    monkeypatch.setattr(fp, "search_nearby", fake_nearby)
    seed = {"place_id": "new-place", "name_ko": "해운대해수욕장", "query": "q",
            "category": "beach", "indoor": False}
    reviews: list[dict] = []
    place, source = fp.build_place(seed, None, STATIONS, reviews)
    assert place["names"] == {"en": "Haeundae Beach"}
    assert (place["lat"], place["lng"]) == HAEUNDAE
    assert {r["lang"] for r in reviews} == {"ja", "zh-Hans", "zh-Hant"}
    assert source["contentids"] == {"ko": "1", "en": "10"}


def test_build_place_신규_장소는_이름이_하나도_없으면_쓰지_않는다(monkeypatch):
    monkeypatch.setattr(fp, "search_keyword", lambda q, p: [cand("1", "해운대해수욕장")])
    monkeypatch.setattr(fp, "search_nearby", lambda *a, **k: [])
    seed = {"place_id": "new-place", "name_ko": "해운대해수욕장", "query": "q",
            "category": "beach", "indoor": False}
    reviews: list[dict] = []
    assert fp.build_place(seed, None, STATIONS, reviews) == (None, None)
    assert [r["lang"] for r in reviews] == ["en", "ja", "zh-Hans", "zh-Hant", "all"]
    assert reviews[-1]["reason"] == "no_names"


def test_build_place_기존_값은_exact일_때만_덮어쓰고_contains는_kept_existing(monkeypatch):
    def fake_nearby(service, lat, lng, raw_path, radius=300):
        if service == "JpnService2":
            return [cand("20", "釜山 国際市場（부산 국제시장）")]  # exact → 덮어쓴다
        if service == "ChsService2":
            return [cand("21", "国际市场美食街(국제시장 먹자골목)")]  # contains, 값이 다름 → 유지 + review
        if service == "ChtService2":
            return [cand("22", "國際市場(국제시장 먹자골목)")]  # contains, 값이 같음 → 유지, review 없음
        return []

    def fake_keyword(keyword, raw_path, service="KorService2"):
        assert service == "KorService2", "기존 영문 값이 있으면 영문 키워드 검색을 하지 않는다"
        return [cand("1", "국제시장")]

    monkeypatch.setattr(fp, "search_keyword", fake_keyword)
    monkeypatch.setattr(fp, "search_nearby", fake_nearby)
    seed = {"place_id": "gukje-market", "name_ko": "국제시장", "query": "국제시장", "category": "market",
            "indoor": False, "keywords": {"en": "Gukje Market"}}
    existing = {"place_id": "gukje-market", "names": {"en": "Gukje Market", "ja": "国際市場",
                "zh-Hans": "国际市场", "zh-Hant": "國際市場"},
                "lat": 1.0, "lng": 1.0, "category": "market", "indoor": False, "nearest_station": "Old"}
    reviews: list[dict] = []
    place, source = fp.build_place(seed, existing, [], reviews)  # 역 목록이 비면 기존 역을 유지
    assert place["place_id"] == "gukje-market" and place["nearest_station"] == "Old"
    assert place["names"] == {"en": "Gukje Market", "ja": "釜山 国際市場", "zh-Hans": "国际市场", "zh-Hant": "國際市場"}
    assert list(place["names"]) == fp.NAME_LANGS
    assert [(r["lang"], r["reason"]) for r in reviews] == [("en", "no_korean_match"), ("zh-Hans", "kept_existing")]
    assert "国际市场美食街" in reviews[1]["candidates"]
    assert source["contentids"] == {"ko": "1", "ja": "20"} and source["match_kind"] == {"ja": "exact"}


def test_build_place_영문은_키워드_검색으로_보완(monkeypatch):
    asked = []

    def fake_keyword(keyword, raw_path, service="KorService2"):
        asked.append((service, keyword, raw_path.name))
        if service == "KorService2":
            return [cand("1", "더베이101")]
        return [cand("30", "Far Bay (먼곳)", lat=HAEUNDAE[0] + 0.006),  # 300m 밖
                cand("31", "The Bay 101 Yacht Club (더베이101 요트클럽)", lat=HAEUNDAE[0] + 0.001),
                cand("32", "The Bay 101 (더베이 101)", lat=HAEUNDAE[0] + 0.0005)]  # 가장 가까움

    monkeypatch.setattr(fp, "search_keyword", fake_keyword)
    monkeypatch.setattr(fp, "search_nearby", lambda *a, **k: [cand("9", "Other (다른곳)")])
    seed = {"place_id": "the-bay-101", "name_ko": "더베이101", "query": "더베이101", "category": "attraction",
            "indoor": False, "keywords": {"en": "The Bay 101"}}
    reviews: list[dict] = []
    place, source = fp.build_place(seed, None, STATIONS, reviews)
    assert place["names"] == {"en": "The Bay 101"}
    assert asked == [("KorService2", "더베이101", "ko.json"), ("EngService2", "The Bay 101", "en_keyword.json")]
    assert source["match_kind"] == {"en": "keyword_en"} and source["contentids"]["en"] == "32"
    assert {r["lang"] for r in reviews} == {"ja", "zh-Hans", "zh-Hant"}


def test_pick_keyword_300m_밖과_빈_이름은_버리고_같은_거리에_다른_이름이면_고르지_않는다():
    kor = cand("1", "롯데프리미엄아울렛 동부산점")
    assert fp.pick_keyword(kor, []) is None
    assert fp.pick_keyword(kor, [cand("2", "Far", lat=HAEUNDAE[0] + 0.006), cand("3", "(한글만)")]) is None
    lap = cand("4", "LAP - Lotte Premium Outlets (LAP 롯데프리미엄아울렛 동부산점)")
    apc = cand("5", "APC - Lotte Premium Outlets (APC 롯데프리미엄아울렛 동부산점)")
    assert fp.pick_keyword(kor, [lap, apc]) is None  # 입점 매장끼리 좌표가 같다
    same = [cand("6", "Busan Tower (부산타워)"), cand("7", "Busan Tower")]  # 이름이 같으면 어느 쪽이든 된다
    assert fp.pick_keyword(kor, same)["name"] == "Busan Tower"
    store = cand("8", "Lotte Premium Outlets", lat=HAEUNDAE[0] + 0.0001)
    assert fp.pick_keyword(kor, [store, cand("9", "Other", lat=HAEUNDAE[0] + 0.001)])["contentid"] == "8"


def test_offline은_저장된_같은_요청의_응답만_다시_읽는다(monkeypatch, tmp_path):
    body = {"response": {"header": {"resultCode": "0000"}, "body": {"items": {"item": {
        "contentid": "1", "title": "A", "addr1": "부산", "mapx": "129.1", "mapy": "35.1"}}}}}
    monkeypatch.setattr(fp, "request_json", lambda *a: body)
    raw = tmp_path / "p" / "ko.json"
    online = fp.search_keyword("부산타워", raw)
    monkeypatch.setattr(fp, "OFFLINE", True)
    monkeypatch.setattr(fp, "request_json", lambda *a: pytest.fail("offline 에서는 호출하지 않는다"))
    assert fp.search_keyword("부산타워", raw) == online
    with pytest.raises(fp.FetchError):
        fp.search_keyword("다른 검색어", raw)  # 저장된 응답과 요청이 다르다
    with pytest.raises(fp.FetchError):
        fp.search_keyword("부산타워", tmp_path / "p" / "none.json")


def test_reuse_raw는_저장된_같은_요청은_다시_부르지_않고_없는_요청만_호출한다(monkeypatch, tmp_path):
    body = {"response": {"header": {"resultCode": "0000"}, "body": {"items": {"item": {
        "contentid": "1", "title": "A", "addr1": "부산", "mapx": "129.1", "mapy": "35.1"}}}}}
    calls = []
    monkeypatch.setattr(fp, "request_json", lambda *a: calls.append(a) or body)
    monkeypatch.setattr(fp, "REUSE_RAW", True)
    raw = tmp_path / "p" / "ko.json"
    first = fp.search_keyword("부산타워", raw)  # 저장된 응답이 없으면 호출한다
    assert fp.search_keyword("부산타워", raw) == first and len(calls) == 1
    fp.search_keyword("다른 검색어", raw)  # 요청이 다르면 호출하고 raw 를 바꾼다
    assert len(calls) == 2 and fp.load_json(raw, {})["params"]["keyword"] == "다른 검색어"


def test_build_place_일문도_시드_키워드가_있으면_키워드_검색으로_보완(monkeypatch):
    asked = []

    def fake_keyword(keyword, raw_path, service="KorService2"):
        asked.append((service, keyword, raw_path.name))
        if service == "KorService2":
            return [cand("1", "해운대시장")]
        if service == "JpnService2":
            return [cand("40", "釜山海雲台市場（부산 해운대시장）", lat=HAEUNDAE[0] + 0.0003)]
        return []  # 영문 키워드는 0건

    monkeypatch.setattr(fp, "search_keyword", fake_keyword)
    monkeypatch.setattr(fp, "search_nearby", lambda *a, **k: [cand("9", "Other (다른곳)")])
    seed = {"place_id": "haeundae-market", "name_ko": "해운대전통시장", "query": "해운대시장", "category": "market",
            "indoor": False, "keywords": {"en": "Haeundae Market", "ja": "海雲台市場"}}
    reviews: list[dict] = []
    place, source = fp.build_place(seed, None, STATIONS, reviews)
    assert place["names"] == {"ja": "釜山海雲台市場"}  # 괄호 안 한국어는 뺀다
    assert asked == [("KorService2", "해운대시장", "ko.json"), ("EngService2", "Haeundae Market", "en_keyword.json"),
                     ("JpnService2", "海雲台市場", "ja_keyword.json")]  # 키워드가 없는 중국어는 호출하지 않는다
    assert source["match_kind"] == {"ja": "keyword_ja"} and source["contentids"]["ja"] == "40"
    assert {r["lang"] for r in reviews} == {"en", "zh-Hans", "zh-Hant"}  # 못 찾은 언어는 review 에 남는다


def test_dump_places_names는_한_줄():
    places = [{"place_id": "a", "names": {"en": "A {x}", "ja": "海雲台（釜山）"}, "lat": 1.0, "lng": 2.0,
               "category": "c", "indoor": False, "nearest_station": None},
              {"place_id": "b", "names": {"zh-Hans": "乙"}, "lat": 1.0, "lng": 2.0,
               "category": "c", "indoor": True, "nearest_station": "S"}]
    text = fp.dump_places(places)
    assert fp.json.loads(text) == places and text.endswith("]\n")
    assert '    "names": { "en": "A {x}", "ja": "海雲台（釜山）" },\n' in text
    assert '    "names": { "zh-Hans": "乙" },\n' in text


def test_search_keyword_서비스와_행_수(monkeypatch, tmp_path):
    seen = {}

    def fake_request(service, operation, extra):
        seen.update(service=service, operation=operation, extra=extra)
        return {"response": {"header": {"resultCode": "0000"}, "body": {"items": ""}}}

    monkeypatch.setattr(fp, "request_json", fake_request)
    fp.search_keyword("Busan Tower", tmp_path / "en_keyword.json", "EngService2")
    assert seen == {"service": "EngService2", "operation": "searchKeyword2",
                    "extra": {"keyword": "Busan Tower", "numOfRows": fp.KEYWORD_ROWS}}


def test_build_place_api_실패시_기존값_유지(monkeypatch):
    def boom(keyword, raw_path):
        raise fp.FetchError("timeout")

    monkeypatch.setattr(fp, "search_keyword", boom)
    existing = {"place_id": "a"}
    seed = {"place_id": "a", "name_ko": "가", "query": "가", "category": "x", "indoor": True}
    reviews: list[dict] = []
    assert fp.build_place(seed, existing, STATIONS, reviews) == (existing, None)
    assert "기존 값 유지" in reviews[0]["reason"]


def test_load_stations_별칭_열(tmp_path):
    f = tmp_path / "s.csv"
    f.write_text("역명,위도,경도\n해운대,35.16,129.15\n", encoding="utf-8")
    assert fp.load_stations(f) == [{"name": "해운대", "lat": 35.16, "lng": 129.15}]
