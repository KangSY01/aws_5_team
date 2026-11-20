"""테스트 공통 설정.

GET·PUT /plan, /plan/check, /plan/{plan_id}/delay 는 app.storage 에서 일정을 읽는다. 그래서 핸들러를 부르는 테스트는
테스트마다 샘플 일정(plan-1)이 들어 있는 새 메모리 저장소를 쓴다.

- 환경 변수(USE_MOCK, DYNAMODB_TABLE)가 없어도 AWS 에 접근하지 않는다.
- USE_MOCK 값은 건드리지 않는다. 조회 도구(app/tools/lookup.py)도 이 값을 읽으므로, 바꾸면 다른 테스트의 전제가 달라진다.
- 한 테스트가 일정을 고쳐도 다음 테스트에 남지 않는다.
- get_weather(USE_MOCK=0)의 날씨 캐시도 실제 DynamoDB 테이블을 만들지 않는다. 캐시를 보는 테스트만 가짜 테이블을 끼운다.
- 저장소 자체 테스트(test_storage*.py)는 실제 get_storage() 와 reset_mock_store() 를 검증하므로 대상에서 뺀다.
- 셸에 KAKAO_REST_API_KEY 가 있어도 get_return_options 가 카카오를 실제로 부르지 않는다 (no_kakao).
"""

from pathlib import Path

import pytest

from app import storage
from app.models.plan import Plan
from app.storage.backends import MemoryBackend
from app.storage.service import Storage
from app.tools import lookup, return_options

SAMPLE_PLAN_PATH = Path(__file__).parents[1] / "app" / "data" / "sample_plan.json"
STORAGE_OWN_TESTS = {"test_storage", "test_storage_aws"}


@pytest.fixture(autouse=True)
def api_storage(request, monkeypatch) -> Storage | None:
    if request.module.__name__.rsplit(".", 1)[-1] in STORAGE_OWN_TESTS:
        return None
    store = Storage(MemoryBackend())
    store.create_plan(Plan.model_validate_json(SAMPLE_PLAN_PATH.read_text(encoding="utf-8")))
    monkeypatch.setattr(storage, "get_storage", lambda: store)  # app.storage 의 모듈 함수가 이 저장소를 쓴다
    return store


@pytest.fixture(autouse=True)
def no_real_weather_cache(monkeypatch) -> None:
    """날씨 캐시 테이블을 못 쓰는 상태로 둔다 (lookup 은 경고만 남기고 캐시 없이 동작한다)."""

    def unavailable():
        raise RuntimeError("테스트에서는 실제 캐시 테이블을 쓰지 않는다")

    monkeypatch.setattr(lookup, "_cache_table", unavailable)


@pytest.fixture(autouse=True)
def no_kakao(monkeypatch) -> None:
    """return_options 가 import 한 fetch_routes 를 None 으로 고정한다 (좌표 추정으로 동작한다).

    카카오 성공을 보는 테스트(test_return_options_kakao.py)는 테스트 안에서 return_options.fetch_routes 를 다시 끼우므로
    그쪽 mock 이 이긴다. test_kakao_route.py 는 kakao_route.fetch_routes 를 직접 부르므로 영향이 없다.
    """
    monkeypatch.setattr(return_options, "fetch_routes", lambda *args, **kwargs: None)


@pytest.fixture(autouse=True)
def no_live_routes(monkeypatch) -> None:
    """실시간 경로(OSM 도보·카카오 대중교통, app/tools/route_path.py)를 테스트에서 부르지 않는다.

    일정 시각은 추정값으로 계산되고 GET /route 는 직선으로 대체된다. 성공 경로는 test_route_path.py 가 직접 끼워 넣는다.
    """
    from app.tools import route_path

    monkeypatch.setattr(route_path, "osm_walk", lambda *args, **kwargs: None)
    monkeypatch.setattr(route_path, "fetch_transit", lambda *args, **kwargs: None)
