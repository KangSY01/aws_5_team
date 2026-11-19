"""조회 도구 (도구 담당). 뼈대 단계: 시그니처만 있다.

config.USE_MOCK 이면 app/data/ 의 샘플·캐시를 쓴다. 외부 API는 타임아웃 5초, 재시도 1회.
TODO(도구 담당): 영업 정보, 이동 시간 조회 도구 추가.
"""

from strands import tool


@tool
def search_places(query: str, category: str | None = None, indoor: bool | None = None) -> list[dict]:
    """부산 관광지를 찾는다. 일정에 넣을 장소나 교체 후보가 필요할 때 쓴다.

    Args:
        query: 찾을 내용 (예: "seafood market", "海が見える場所")
        category: 장소 분류로 좁힐 때 (예: beach, market, temple)
        indoor: True면 실내만, False면 실외만, None이면 전부

    Returns:
        Place 형식 dict 목록 (place_id, names, lat, lng, category, indoor, nearest_station).
        결과에 없는 장소는 답변에 쓰지 않는다.
    """
    raise NotImplementedError("TODO(도구 담당)")


@tool
def get_weather(date: str) -> dict:
    """부산의 해당 날짜 시간대별 예보를 가져온다. 비 여부를 확인할 때 쓴다.

    Args:
        date: 날짜 (YYYY-MM-DD)

    Returns:
        시간대별 강수확률·강수량. TODO(도구 담당): 형식 확정.
    """
    raise NotImplementedError("TODO(도구 담당)")


@tool
def get_crowd(place_id: str, date: str) -> dict:
    """장소의 해당 날짜 혼잡 정도를 가져온다. 언제 붐비는지 확인할 때 쓴다.

    Args:
        place_id: 장소 ID (search_places 결과의 값)
        date: 날짜 (YYYY-MM-DD)

    Returns:
        집중률 또는 요일 규칙에 따른 혼잡 정도. 집중률은 그 장소 안에서의 상대값이라
        장소끼리 비교하면 안 된다. TODO(도구 담당): 형식 확정.
    """
    raise NotImplementedError("TODO(도구 담당)")
