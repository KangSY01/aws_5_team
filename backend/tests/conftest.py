"""테스트 공통 설정.

GET·PUT /plan, /plan/check, /plan/{plan_id}/delay 는 app.storage 에서 일정을 읽는다. 그래서 핸들러를 부르는 테스트는
테스트마다 샘플 일정(plan-1)이 들어 있는 새 메모리 저장소를 쓴다.

- 환경 변수(USE_MOCK, DYNAMODB_TABLE)가 없어도 AWS 에 접근하지 않는다.
- USE_MOCK 값은 건드리지 않는다. 조회 도구(app/tools/lookup.py)도 이 값을 읽으므로, 바꾸면 다른 테스트의 전제가 달라진다.
- 한 테스트가 일정을 고쳐도 다음 테스트에 남지 않는다.
- 저장소 자체 테스트(test_storage*.py)는 실제 get_storage() 와 reset_mock_store() 를 검증하므로 대상에서 뺀다.
"""

from pathlib import Path

import pytest

from app import storage
from app.models.plan import Plan
from app.storage.backends import MemoryBackend
from app.storage.service import Storage

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
