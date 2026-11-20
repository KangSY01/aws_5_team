"""저장 백엔드. 일정·세션 규칙은 service.py 에 두고, 여기서는 항목(dict) 하나를 쓰고 읽기만 한다.

항목 모양은 DynamoDB 단일 테이블과 같다: {"pk": "PLAN#<id>" 또는 "SESSION#<id>", "sk": "META", ...속성}.
메모리 백엔드도 같은 모양으로, JSON 으로 표현 가능한 값만 담아 DynamoDB 경로와 같은 제약을 받는다.
"""

import copy
import threading
from typing import Any, Protocol

SORT_KEY = "META"  # 항목 하나당 sk 하나. 같은 pk 아래 다른 종류(예: 예약 점검 결과)를 더할 때 값을 늘린다


class ItemExists(Exception):
    """create 가 이미 있는 항목을 만났다."""


class ItemMissing(Exception):
    """replace·update 가 없는 항목을 만났다."""


class Backend(Protocol):
    def get(self, pk: str) -> dict[str, Any] | None: ...

    def create(self, pk: str, attrs: dict[str, Any]) -> None:
        """없을 때만 쓴다. 있으면 ItemExists."""

    def replace(self, pk: str, attrs: dict[str, Any]) -> None:
        """있을 때만 통째로 바꾼다. 없으면 ItemMissing."""

    def update(self, pk: str, values: dict[str, Any]) -> None:
        """있을 때만 일부 속성을 바꾼다. 없으면 ItemMissing."""


def make_item(pk: str, attrs: dict[str, Any]) -> dict[str, Any]:
    return {"pk": pk, "sk": SORT_KEY, **attrs}


class MemoryBackend:
    """USE_MOCK=1 용. 프로세스 메모리에만 있고 AWS 에 접근하지 않는다.

    쓸 때와 읽을 때 모두 복사하므로, 호출자가 넘기거나 받은 객체를 고쳐도 저장된 값은 바뀌지 않는다.
    """

    def __init__(self):
        self._items: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def get(self, pk: str) -> dict[str, Any] | None:
        with self._lock:
            item = self._items.get(pk)
            return copy.deepcopy(item) if item is not None else None

    def create(self, pk: str, attrs: dict[str, Any]) -> None:
        with self._lock:
            if pk in self._items:
                raise ItemExists(pk)
            self._items[pk] = copy.deepcopy(make_item(pk, attrs))

    def replace(self, pk: str, attrs: dict[str, Any]) -> None:
        with self._lock:
            if pk not in self._items:
                raise ItemMissing(pk)
            self._items[pk] = copy.deepcopy(make_item(pk, attrs))

    def update(self, pk: str, values: dict[str, Any]) -> None:
        with self._lock:
            if pk not in self._items:
                raise ItemMissing(pk)
            self._items[pk].update(copy.deepcopy(values))
