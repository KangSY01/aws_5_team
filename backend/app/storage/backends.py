"""저장 백엔드. 일정·세션·알림 규칙은 service.py 에 두고, 여기서는 항목(dict)을 쓰고 읽기만 한다.

항목 모양은 DynamoDB 단일 테이블과 같다: {"pk": "PLAN#<id>" 또는 "SESSION#<id>", "sk": "META" 또는 "ALERTS", ...속성}.
메모리 백엔드도 같은 모양으로, JSON 으로 표현 가능한 값만 담아 DynamoDB 경로와 같은 제약을 받는다.
sk 를 주지 않으면 기본값 META 다 (기존 호출은 그대로 동작한다).
"""

import copy
import threading
from typing import Any, Protocol

SORT_KEY = "META"  # 일정·세션 본체. 같은 pk 아래 다른 종류(예: 예약 점검 결과 ALERTS)는 sk 를 달리해 따로 둔다


class ItemExists(Exception):
    """create 가 이미 있는 항목을 만났다."""


class ItemMissing(Exception):
    """replace·update 가 없는 항목을 만났다."""


class Backend(Protocol):
    def get(self, pk: str, sk: str = SORT_KEY) -> dict[str, Any] | None: ...

    def create(self, pk: str, attrs: dict[str, Any], sk: str = SORT_KEY) -> None:
        """없을 때만 쓴다. 있으면 ItemExists."""

    def replace(self, pk: str, attrs: dict[str, Any], sk: str = SORT_KEY) -> None:
        """있을 때만 통째로 바꾼다. 없으면 ItemMissing."""

    def update(self, pk: str, values: dict[str, Any], sk: str = SORT_KEY) -> None:
        """있을 때만 일부 속성을 바꾼다. 없으면 ItemMissing."""

    def put(self, pk: str, attrs: dict[str, Any], sk: str = SORT_KEY) -> None:
        """있든 없든 통째로 쓴다 (덮어쓰기). 같은 pk 의 다른 sk 항목은 건드리지 않는다."""

    def list_pks(self, prefix: str, sk: str = SORT_KEY) -> list[str]:
        """pk 가 prefix 로 시작하고 sk 가 일치하는 항목의 pk 를 정렬해 돌려준다. 다른 sk 항목은 빼고, 끝까지(페이지 모두) 읽는다."""


def make_item(pk: str, attrs: dict[str, Any], sk: str = SORT_KEY) -> dict[str, Any]:
    return {"pk": pk, "sk": sk, **attrs}


class MemoryBackend:
    """USE_MOCK=1 용. 프로세스 메모리에만 있고 AWS 에 접근하지 않는다.

    쓸 때와 읽을 때 모두 복사하므로, 호출자가 넘기거나 받은 객체를 고쳐도 저장된 값은 바뀌지 않는다.
    """

    def __init__(self):
        self._items: dict[tuple[str, str], dict[str, Any]] = {}  # (pk, sk) → 항목
        self._lock = threading.Lock()

    def get(self, pk: str, sk: str = SORT_KEY) -> dict[str, Any] | None:
        with self._lock:
            item = self._items.get((pk, sk))
            return copy.deepcopy(item) if item is not None else None

    def create(self, pk: str, attrs: dict[str, Any], sk: str = SORT_KEY) -> None:
        with self._lock:
            if (pk, sk) in self._items:
                raise ItemExists(pk)
            self._items[(pk, sk)] = copy.deepcopy(make_item(pk, attrs, sk))

    def replace(self, pk: str, attrs: dict[str, Any], sk: str = SORT_KEY) -> None:
        with self._lock:
            if (pk, sk) not in self._items:
                raise ItemMissing(pk)
            self._items[(pk, sk)] = copy.deepcopy(make_item(pk, attrs, sk))

    def update(self, pk: str, values: dict[str, Any], sk: str = SORT_KEY) -> None:
        with self._lock:
            if (pk, sk) not in self._items:
                raise ItemMissing(pk)
            self._items[(pk, sk)].update(copy.deepcopy(values))

    def put(self, pk: str, attrs: dict[str, Any], sk: str = SORT_KEY) -> None:
        with self._lock:
            self._items[(pk, sk)] = copy.deepcopy(make_item(pk, attrs, sk))

    def list_pks(self, prefix: str, sk: str = SORT_KEY) -> list[str]:
        with self._lock:
            return sorted(pk for (pk, item_sk) in self._items if item_sk == sk and pk.startswith(prefix))
