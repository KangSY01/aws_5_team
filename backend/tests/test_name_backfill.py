"""scripts/backfill_names.py 테스트. 네트워크를 쓰지 않고 실제 app/data/ 파일도 읽거나 쓰지 않는다.

속성 테스트는 hypothesis 없이 pytest.mark.parametrize 로 한다. 입력은 손으로 고른 경계 케이스와
random.Random(고정 시드) 난수 입력을 합쳐 중복을 없앤 100개 이상이다. 입력 개수는 속성마다 길이 확인 테스트가 지킨다.

파일 위쪽 「공용 구역」의 후보·장소 생성 헬퍼와 입력 목록은 뒤에 추가되는 속성 테스트가 같이 쓴다.
"""
import copy
import json
import random

import pytest

from scripts import backfill_names as bn

MIN_CASES = 100  # 속성마다 필요한 입력 개수 (중복 제거 후)
SEED = 20240601  # 난수 입력의 고정 시드. 바꾸면 입력이 달라지므로 실패를 재현하려면 그대로 둔다
RANDOM_CASES = 150  # 난수로 만드는 입력 개수 (중복 제거 전에 이만큼 만든다)

# 위도 1도 ≈ 111km 이므로 0.00001도 ≈ 1.1m. 거리가 얼마인 후보를 만들지 계산하는 데 쓴다
M_PER_LAT_DEG = 111_000
KOR_TITLE = "해리단길"
BASE_LAT, BASE_LNG = 35.1630, 129.1590


# ---------- 공용 구역: 후보·장소 생성 헬퍼 (뒤 작업의 속성 테스트가 재사용한다) ----------

def make_kor(title: str = KOR_TITLE, lat: float = BASE_LAT, lng: float = BASE_LNG) -> dict:
    """국문 기준 {title, lat, lng}."""
    return {"title": title, "lat": lat, "lng": lng}


def make_candidate(contentid: object, title: object, dist_m: float = 0.0, kor: dict | None = None) -> dict:
    """기준 좌표에서 북쪽으로 dist_m 미터 떨어진 후보 하나. parse_items 형식 {contentid, title, addr1, lat, lng}."""
    base = kor or make_kor()
    return {"contentid": str(contentid), "title": title, "addr1": "부산광역시 해운대구",
            "lat": base["lat"] + dist_m / M_PER_LAT_DEG, "lng": base["lng"]}


def make_place(names: dict | None = None, kor: dict | None = None, **overrides) -> dict:
    """장소 dict. names 외 필드(place_id, name_ko, lat, lng, category, indoor, nearest_station)를 모두 채운다."""
    base = kor or make_kor()
    place = {"place_id": "haeridan-gil", "name_ko": base["title"], "lat": base["lat"], "lng": base["lng"],
             "category": "street", "indoor": False, "nearest_station": "haeundae", "names": dict(names or {})}
    place.update(overrides)
    return place


def bad_candidates() -> list:
    """쓸 수 없는 후보 모음: title None·빈 문자열·공백뿐, 필드 누락, dict 아님."""
    good = make_candidate(9, f"Bad ({KOR_TITLE})")
    return [
        {**good, "title": None},
        {**good, "title": ""},
        {**good, "title": "   "},
        {k: v for k, v in good.items() if k != "title"},
        {k: v for k, v in good.items() if k != "contentid"},
        {k: v for k, v in good.items() if k != "lat"},
        {**good, "lng": None},
        None,
        "문자열",
        42,
    ]


def case_key(case: dict) -> str:
    """중복 제거용 키. 입력이 같으면 같은 문자열이다."""
    return json.dumps(case, sort_keys=True, ensure_ascii=False, default=repr)


def dedupe_cases(cases: list[dict]) -> list[dict]:
    """같은 입력을 하나만 남긴다. 순서는 유지한다."""
    seen: set[str] = set()
    unique = []
    for case in cases:
        key = case_key(case)
        if key not in seen:
            seen.add(key)
            unique.append(case)
    return unique


def make_case(place: dict, candidates: dict, kor: dict | None = None) -> dict:
    """fill_names 입력 한 벌. place 의 names·좌표가 입력의 기준이다."""
    return {"place": place, "kor": kor or make_kor(place["name_ko"], place["lat"], place["lng"]), "candidates": candidates}


def run_fill(case: dict, known_reviews: frozenset = frozenset()) -> "bn.FillResult":
    """case 로 fill_names 를 부른다. 입력은 복사해서 넘기므로 case 는 바뀌지 않는다."""
    place = copy.deepcopy(case["place"])
    return bn.fill_names(place["place_id"], place["name_ko"], copy.deepcopy(case["kor"]), place["names"],
                         copy.deepcopy(case["candidates"]), known_reviews)


def _manual_cases() -> list[dict]:
    """손으로 고른 경계 케이스."""
    good = make_candidate(100, f"Haeridan-gil ({KOR_TITLE})", 50)
    other = make_candidate(101, "Somewhere Else", 20)
    all_langs = {lang: [good] for lang in bn.NAME_LANGS}
    full_names = {"en": "Existing EN", "ja": "既存", "zh-Hans": "现有", "zh-Hant": "現有"}
    cases = [
        make_case(make_place(), {}),  # 후보 키 없음(전 언어 수집 실패)
        make_case(make_place(), {lang: [] for lang in bn.NAME_LANGS}),  # 후보 0건
        make_case(make_place(), all_langs),  # 전 언어 채움
        make_case(make_place(full_names), all_langs),  # 이미 다 있음
        make_case(make_place({"ja": "既存の名前"}), all_langs),  # 일부만 있음: ja 는 그대로
        make_case(make_place({"en": "Keep Me", "ja": "既存"}), {"ja": [good], "zh-Hans": [good]}),
        make_case(make_place({"ja": "   "}), all_langs),  # 공백뿐인 이름은 빠진 값(채워진다)
        make_case(make_place({"ja": ""}), all_langs),  # 빈 문자열 이름도 빠진 값
        make_case(make_place({"ko": "한글 키", "ja": "既存"}), all_langs),  # NAME_LANGS 밖의 키도 그대로
        make_case(make_place({"ja": "既存"}), {"ja": [other]}),  # 일치 후보 없음
        make_case(make_place(), {"ja": [make_candidate(100, KOR_TITLE)]}),  # 한글만 있는 title → 이름 없음
        make_case(make_place(), {"ja": [make_candidate(100, f"({KOR_TITLE})")]}),  # 한국어를 빼면 빔
        make_case(make_place(), {"ja": bad_candidates()}),  # 불량 후보만
        make_case(make_place(), {"ja": [*bad_candidates(), good]}),  # 불량 후보 + 정상 후보
        make_case(make_place(), {"ja": None}),  # 후보 목록 자체가 목록이 아님
        make_case(make_place(), {"ja": [make_candidate(1, f"A ({KOR_TITLE})", 100), make_candidate(2, f"B ({KOR_TITLE})", 100)]}),  # 거리 동률
        make_case(make_place(), {"ja": [make_candidate(1, f"A ({KOR_TITLE})", 100), make_candidate(2, f"B ({KOR_TITLE})", 200)]}),  # 이름이 달라 모호
        make_case(make_place(), {"ja": [make_candidate(1, f"A ({KOR_TITLE})", 800)]}),  # 1000m 반경에서만 일치
        make_case(make_place(), {"ja": [make_candidate(1, f"A ({KOR_TITLE})", 1500)]}),  # 반경 밖
        make_case(make_place(category=None, indoor=None, nearest_station=None), all_langs),  # 비어 있는 부가 필드
        make_case(make_place(indoor=True, category="museum", nearest_station="centum-city", tags=["a", "b"]), all_langs),  # 추가 필드
        make_case(make_place(lat=0.0, lng=0.0), all_langs, kor=make_kor(lat=0.0, lng=0.0)),  # 원점 좌표
    ]
    # 언어마다 서로 다른 후보를 줘서 일부 언어만 채워지는 경우
    for lang in bn.NAME_LANGS:
        cases.append(make_case(make_place(), {lang: [good], **{o: [other] for o in bn.NAME_LANGS if o != lang}}))
    # 기존 이름이 있는 언어를 한 개씩 번갈아 둔 경우
    for lang in bn.NAME_LANGS:
        cases.append(make_case(make_place({lang: f"Existing {lang}"}), all_langs))
    return cases


def _random_candidate(rng: random.Random, serial: int, kor: dict) -> object:
    """난수 후보 하나. 일치하는 것, 일치하지 않는 것, 쓸 수 없는 것이 섞인다."""
    kind = rng.choice(["match", "match", "match", "other", "korean_only", "blank", "missing", "not_dict"])
    foreign = rng.choice(["Haeri", "海里", "ヘリ", "Café", "Sea View", "Stand"])
    dist = rng.choice([0, 10, 50, 120, 299, 301, 600, 999, 1001, 1500])
    cand = make_candidate(rng.choice([serial, serial, 100 + serial]), "", dist, kor)
    if kind == "match":
        cand["title"] = rng.choice([f"{foreign} ({kor['title']})", f"{foreign}（{kor['title']}）", f"{foreign} {kor['title']}"])
    elif kind == "other":
        cand["title"] = f"{foreign} 다른곳"
    elif kind == "korean_only":
        cand["title"] = kor["title"]
    elif kind == "blank":
        cand["title"] = rng.choice([None, "", "  "])
    elif kind == "missing":
        del cand[rng.choice(["title", "contentid", "lat", "lng"])]
    else:
        return rng.choice([None, "문자열", 7, [1, 2]])
    return cand


def _random_cases(count: int) -> list[dict]:
    """random.Random(SEED) 로 만든 난수 입력. 같은 시드이므로 실행할 때마다 같다."""
    rng = random.Random(SEED)
    cases = []
    for index in range(count):
        kor = make_kor(rng.choice([KOR_TITLE, "광안리해수욕장", "BIFF광장"]),
                       round(rng.uniform(35.0, 35.3), 5), round(rng.uniform(129.0, 129.2), 5))
        names = {}
        for lang in bn.NAME_LANGS:
            roll = rng.random()
            if roll < 0.3:
                names[lang] = rng.choice(["Existing", "既存の名前", "现有名称", "現有名稱"])
            elif roll < 0.4:
                names[lang] = rng.choice(["", " ", "   "])  # 빠진 값으로 취급되는 이름
        if rng.random() < 0.15:
            names["ko"] = "한글 키"
        place = make_place(names, kor, place_id=f"p{index}",
                           category=rng.choice([None, "street", "museum", "market"]),
                           indoor=rng.choice([None, True, False]),
                           nearest_station=rng.choice([None, "haeundae", "nampo"]))
        candidates = {}
        for lang in bn.NAME_LANGS:
            if rng.random() < 0.85:  # 나머지 언어는 후보 키가 없다(수집 실패)
                candidates[lang] = [_random_candidate(rng, n, kor) for n in range(rng.randint(0, 5))]
        cases.append(make_case(place, candidates, kor))
    return cases


ALL_CASES = dedupe_cases(_manual_cases() + _random_cases(RANDOM_CASES))
CASE_IDS = [f"case{index:03d}" for index in range(len(ALL_CASES))]


# ---------- Property 1: 채우기는 기존 값을 바꾸지 않는다 ----------

def test_속성_입력은_중복을_뺀_100개_이상이다():
    assert len(ALL_CASES) >= MIN_CASES
    assert len({case_key(case) for case in ALL_CASES}) == len(ALL_CASES)


def test_속성_입력은_경계_케이스와_난수를_모두_포함한다():
    manual = dedupe_cases(_manual_cases())
    assert len(manual) >= 20 and len(ALL_CASES) - len(manual) >= MIN_CASES // 2
    assert _random_cases(RANDOM_CASES) == _random_cases(RANDOM_CASES)  # 고정 시드라 매번 같다


def test_속성_입력에는_실제로_채워지는_경우와_안_채워지는_경우가_모두_있다():
    """채워지는 입력이 없으면 속성 검증이 아무것도 확인하지 못하므로 입력 구성을 점검한다."""
    filled = [bool(run_fill(case).filled) for case in ALL_CASES]
    assert sum(filled) >= MIN_CASES // 2
    assert not all(filled)


# Feature: name-backfill, Property 1: 채우기는 기존 값을 바꾸지 않는다
# Validates: Requirements 2.5, 2.6, 10.2
@pytest.mark.parametrize("case", ALL_CASES, ids=CASE_IDS)
def test_속성1_채우기는_기존_이름과_다른_필드를_바꾸지_않는다(case):
    place = case["place"]
    before = copy.deepcopy(place)
    result = run_fill(case)

    # fill_names: 기존 names 의 키·값이 그대로 남는다. 값이 공백뿐인 이름은 빠진 값이라 채워질 수 있어 제외한다
    for lang, value in place["names"].items():
        if isinstance(value, str) and value.strip():
            assert result.names[lang] == value, f"{lang} 이름이 바뀜"
        else:  # 공백뿐인 이름: 키는 그대로 있고, 채워지지 않았다면 값도 그대로다
            assert lang in result.names
            if lang not in result.filled:
                assert result.names[lang] == value
    # 새로 생긴 키는 이번에 채운 언어뿐이다
    assert set(result.names) - set(place["names"]) <= set(result.filled)

    # apply_fill: names 외 필드는 입력과 같고, 입력 dict 자체도 바뀌지 않는다
    applied = bn.apply_fill(place, result)
    for key in ("place_id", "lat", "lng", "category", "indoor", "nearest_station"):
        assert applied[key] == before[key]
    assert {k: v for k, v in applied.items() if k != "names"} == {k: v for k, v in before.items() if k != "names"}
    assert applied["names"] == result.names
    assert place == before


# ---------- Property 2: 같은 입력으로 다시 적용해도 결과가 같다 ----------

def test_속성2_입력은_중복을_뺀_100개_이상이다():
    # Property 2 는 공용 입력 ALL_CASES 를 그대로 쓰므로 개수와 중복 없음을 여기서도 확인한다
    assert len(ALL_CASES) >= MIN_CASES
    assert len({case_key(case) for case in ALL_CASES}) == len(ALL_CASES)


def test_속성2_입력에는_review_행이_생기는_경우와_안_생기는_경우가_모두_있다():
    """첫 결과에 review 행이 하나도 없으면 known_reviews 경로를 확인하지 못하므로 입력 구성을 점검한다."""
    with_review = [bool(run_fill(case).reviews) for case in ALL_CASES]
    assert sum(with_review) >= MIN_CASES // 2
    assert not all(with_review)


# Feature: name-backfill, Property 2: 같은 입력으로 다시 적용해도 결과가 같다
# Validates: Requirements 10.3
@pytest.mark.parametrize("case", ALL_CASES, ids=CASE_IDS)
def test_속성2_같은_입력으로_다시_적용하면_이름이_같고_새_review_행이_없다(case):
    first = run_fill(case)
    known = frozenset((row["place_id"], row["lang"]) for row in first.reviews)

    # 첫 결과의 names 를 기존 names 로 삼고, 같은 후보 목록과 known_reviews 로 다시 적용한다
    again_case = make_case({**case["place"], "names": dict(first.names)}, case["candidates"], case["kor"])
    second = run_fill(again_case, known)

    assert second.names == first.names
    assert list(second.names) == list(first.names)  # 키 순서도 같다
    assert second.reviews == []  # 새 review 행 0건
    assert second.filled == {}  # 두 번째에는 새로 채워지는 언어도 없다


# ---------- Property 3: 이름은 후보 title 의 strip_korean 값뿐이다 ----------

def _allowed_names(cands: object) -> set[str]:
    """후보 목록에서 나올 수 있는 이름 집합. title 이 문자열인 dict 후보의 strip_korean 값(빈 문자열 제외).

    fill_names 의 sanitize_candidates 를 쓰지 않고 원본 후보를 직접 읽는다. 구현과 별개의 기준으로 확인하기 위해서다.
    """
    if not isinstance(cands, (list, tuple)):
        return set()
    names = {bn.strip_korean(c["title"]) for c in cands if isinstance(c, dict) and isinstance(c.get("title"), str)}
    return {name for name in names if name}


def test_속성3_입력은_중복을_뺀_100개_이상이다():
    # Property 3 도 공용 입력 ALL_CASES 를 그대로 쓰므로 개수와 중복 없음을 여기서도 확인한다
    assert len(ALL_CASES) >= MIN_CASES
    assert len({case_key(case) for case in ALL_CASES}) == len(ALL_CASES)


def test_속성3_입력에는_후보가_빈_언어와_이름이_채워지는_언어가_모두_있다():
    """후보가 빈 경우와 채워지는 경우가 모두 없으면 속성의 양쪽 갈래를 확인하지 못하므로 입력 구성을 점검한다."""
    empty_langs = filled_langs = 0
    for case in ALL_CASES:
        result = run_fill(case)
        for lang in bn.NAME_LANGS:
            if lang not in case["candidates"]:
                continue
            if not _allowed_names(case["candidates"][lang]):
                empty_langs += 1
            elif lang in result.filled:
                filled_langs += 1
    assert empty_langs >= MIN_CASES // 2
    assert filled_langs >= MIN_CASES // 2


# Feature: name-backfill, Property 3: 이름은 후보 title의 strip_korean 값뿐이다
# Validates: Requirements 2.2, 2.9, 10.4
@pytest.mark.parametrize("case", ALL_CASES, ids=CASE_IDS)
def test_속성3_새로_채운_이름은_후보_title의_strip_korean_값이다(case):
    original = case["place"]["names"]
    result = run_fill(case)

    # 새로 채운 언어: 입력에 없었거나 값이 달라진 키. 이 집합은 result.filled 와 정확히 같아야 한다
    newly = {lang for lang, value in result.names.items() if original.get(lang) != value}
    assert newly == set(result.filled)

    for lang in newly:
        name = result.names[lang]
        allowed = _allowed_names(case["candidates"].get(lang))
        assert isinstance(name, str) and name.strip(), f"{lang} 이름이 비어 있음"  # 비어 있지 않다
        assert name in allowed, f"{lang} 이름 {name!r} 이 후보 title 의 strip_korean 값이 아님"  # 정확히 같다
        assert result.filled[lang].name == name

    # 후보 목록이 비어 있거나(후보 0건, 목록 아님) 키가 없는 언어는 새로 채운 이름이 0건이다
    for lang in bn.NAME_LANGS:
        if not _allowed_names(case["candidates"].get(lang)):
            assert lang not in newly, f"{lang}: 후보가 없는데 이름이 채워짐"
