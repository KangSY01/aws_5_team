"""일정 부분 수정 도구 (도구 담당). 뼈대 단계: 시그니처만 있다.

일정은 전체를 다시 만들지 않고 이 도구들로만 고친다.
모든 도구는 locked=true 인 Stop 을 바꾸려 하면 거부하고, 결과를 StopChange 형식으로 돌려준다.
TODO(도구 담당): 현재 일정을 도구에 넘기는 방법을 에이전트 담당과 정한다.
"""

from strands import tool


@tool
def replace_stop(stop_id: str, new_place_id: str) -> dict:
    """Stop 의 장소를 다른 장소로 바꾼다. 시간은 그대로 둔다.

    Args:
        stop_id: 바꿀 Stop 의 ID
        new_place_id: 새 장소 ID (search_places 결과의 값)

    Returns:
        StopChange 형식 dict (stop_id, before, after)
    """
    raise NotImplementedError("TODO(도구 담당)")


@tool
def add_stop(place_id: str, start: str, end: str) -> dict:
    """일정에 Stop 을 추가한다.

    Args:
        place_id: 추가할 장소 ID (search_places 결과의 값)
        start: 시작 시각 (시간대 포함 ISO 8601)
        end: 종료 시각 (시간대 포함 ISO 8601)

    Returns:
        StopChange 형식 dict (before 는 null)
    """
    raise NotImplementedError("TODO(도구 담당)")


@tool
def remove_stop(stop_id: str) -> dict:
    """일정에서 Stop 을 뺀다.

    Args:
        stop_id: 뺄 Stop 의 ID

    Returns:
        StopChange 형식 dict (after 는 null)
    """
    raise NotImplementedError("TODO(도구 담당)")


@tool
def move_stop(stop_id: str, start: str, end: str) -> dict:
    """Stop 의 시간을 옮긴다. 장소는 그대로 둔다.

    Args:
        stop_id: 옮길 Stop 의 ID
        start: 새 시작 시각 (시간대 포함 ISO 8601)
        end: 새 종료 시각 (시간대 포함 ISO 8601)

    Returns:
        StopChange 형식 dict (stop_id, before, after)
    """
    raise NotImplementedError("TODO(도구 담당)")
