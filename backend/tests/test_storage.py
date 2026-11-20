"""app/storage 일정·세션 저장소. AWS 자격 증명과 네트워크 없이 돈다.

핵심 동작은 메모리 백엔드와 DynamoDB 백엔드(가짜 테이블 주입) 양쪽에서 같은 테스트로 확인한다.
"""

import copy
import logging
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from boto3.dynamodb.types import TypeSerializer
from botocore.exceptions import ClientError, EndpointConnectionError

from app import config, storage
from app.models.plan import Plan, Profile
from app.storage import dynamodb
from app.storage.backends import MemoryBackend
from app.storage.dynamodb import DynamoBackend
from app.storage.errors import (
    InvalidDataError,
    PlanAccessDeniedError,
    PlanAlreadyExistsError,
    PlanNotFoundError,
    SessionNotFoundError,
    StorageError,
)
from app.storage.models import SessionState
from app.storage.service import Storage

SAMPLE_PLAN_JSON = (Path(__file__).parents[1] / "app" / "data" / "sample_plan.json").read_text(encoding="utf-8")
KST = timezone(timedelta(hours=9))
START = datetime(2026, 11, 21, 9, 0, tzinfo=KST)


class FakeTable:
    """boto3 Table 대역. DynamoDB 의 조건식·직렬화 제약을 흉내 내고 호출을 기록한다."""

    def __init__(self, fail_with: Exception | None = None):
        self.items: dict[tuple[str, str], dict] = {}
        self.calls: list[tuple[str, dict]] = []
        self.fail_with = fail_with
        self.page_size = 1000  # scan 한 번에 읽는 항목 수 (테스트에서 줄여 페이지 이어 읽기를 확인한다)

    def _enter(self, name: str, **kwargs):
        self.calls.append((name, kwargs))
        if self.fail_with is not None:
            raise self.fail_with

    @staticmethod
    def _condition_failed(operation: str) -> ClientError:
        return ClientError({"Error": {"Code": "ConditionalCheckFailedException", "Message": "조건 실패"}}, operation)

    def get_item(self, Key, ConsistentRead=False):
        self._enter("get_item", Key=Key, ConsistentRead=ConsistentRead)
        item = self.items.get((Key["pk"], Key["sk"]))
        return {"Item": copy.deepcopy(item)} if item is not None else {}

    def put_item(self, Item, ConditionExpression=None):
        self._enter("put_item", Item=Item, ConditionExpression=ConditionExpression)
        TypeSerializer().serialize(Item)  # float 등 DynamoDB 가 받지 않는 값이면 TypeError
        exists = (Item["pk"], Item["sk"]) in self.items
        if (ConditionExpression == "attribute_not_exists(pk)" and exists) or (
            ConditionExpression == "attribute_exists(pk)" and not exists
        ):
            raise self._condition_failed("PutItem")
        self.items[(Item["pk"], Item["sk"])] = copy.deepcopy(Item)

    def scan(self, FilterExpression, ProjectionExpression, ExpressionAttributeNames, ExpressionAttributeValues,
             ConsistentRead=False, ExclusiveStartKey=None):
        """페이지 크기 page_size 개씩 돌려주는 Scan 대역. begins_with(pk) AND sk 필터만 지원한다."""
        self._enter("scan", Filter=FilterExpression, Projection=ProjectionExpression, ConsistentRead=ConsistentRead,
                    ExclusiveStartKey=ExclusiveStartKey)
        assert FilterExpression == "begins_with(#pk, :prefix) AND #sk = :sk"
        assert ExpressionAttributeNames == {"#pk": "pk", "#sk": "sk"}
        keys = sorted(self.items)  # (pk, sk) 순서로 읽는다
        start = keys.index(tuple(ExclusiveStartKey.values())) + 1 if ExclusiveStartKey else 0
        page = keys[start:start + self.page_size]
        items = [{"pk": pk} for pk, sk in page
                 if pk.startswith(ExpressionAttributeValues[":prefix"]) and sk == ExpressionAttributeValues[":sk"]]
        more = start + self.page_size < len(keys)
        response = {"Items": items}
        if more:
            response["LastEvaluatedKey"] = {"pk": page[-1][0], "sk": page[-1][1]}
        return response

    def update_item(self, Key, UpdateExpression, ExpressionAttributeNames, ExpressionAttributeValues, ConditionExpression):
        self._enter("update_item", Key=Key, UpdateExpression=UpdateExpression, Names=ExpressionAttributeNames)
        assert ConditionExpression == "attribute_exists(pk)"
        key = (Key["pk"], Key["sk"])
        if key not in self.items:
            raise self._condition_failed("UpdateItem")
        for target, placeholder in re.findall(r"(#a\d+) = (:v\d+)", UpdateExpression):
            TypeSerializer().serialize(ExpressionAttributeValues[placeholder])
            self.items[key][ExpressionAttributeNames[target]] = copy.deepcopy(ExpressionAttributeValues[placeholder])


class Clock:
    def __init__(self):
        self.now = START

    def __call__(self) -> datetime:
        return self.now

    def advance(self, minutes: int) -> None:
        self.now += timedelta(minutes=minutes)


def make_plan(plan_id: str = "plan-a") -> Plan:
    return Plan.model_validate_json(SAMPLE_PLAN_JSON).model_copy(update={"plan_id": plan_id})


def make_profile(language: str = "en") -> Profile:
    return Profile(language=language, interests=["food"], companions="solo")


@pytest.fixture(autouse=True)
def mock_mode(monkeypatch):
    monkeypatch.setattr(config, "USE_MOCK", True)
    storage.reset_mock_store()


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture(params=["memory", "dynamodb"])
def store(request, clock) -> Storage:
    backend = MemoryBackend() if request.param == "memory" else DynamoBackend(FakeTable())
    return Storage(backend, clock=clock)


def raw_item(store: Storage, pk: str) -> dict:
    backend = store._backend
    return backend._items[(pk, "META")] if isinstance(backend, MemoryBackend) else backend._table.items[(pk, "META")]


# ---- 메모리 백엔드 ----


def test_memory_backend_copies_on_write_and_read():
    backend = MemoryBackend()
    attrs = {"plan": {"stops": ["s1"]}}
    backend.create("PLAN#x", attrs)
    attrs["plan"]["stops"].append("changed")  # 넘긴 값을 고쳐도

    got = backend.get("PLAN#x")
    assert got == {"pk": "PLAN#x", "sk": "META", "plan": {"stops": ["s1"]}}
    got["plan"]["stops"].append("changed")  # 읽은 값을 고쳐도
    assert backend.get("PLAN#x")["plan"]["stops"] == ["s1"]


# ---- 일정 ----


def test_plan_save_then_get(store):
    plan = make_plan()
    store.create_plan(plan)
    loaded = store.get_plan("plan-a")
    assert loaded == plan
    # 시간대 오프셋과 날짜가 그대로 돌아온다
    assert loaded.stops[0].start.isoformat() == "2026-11-21T10:00:00+09:00"
    assert loaded.date.isoformat() == "2026-11-21"


def test_plan_update_then_get(store):
    store.create_plan(make_plan())
    changed = make_plan()
    changed.stops[3] = changed.stops[3].model_copy(update={"place_id": "shinsegae-centum-city"})
    store.update_plan(changed)

    loaded = store.get_plan("plan-a")
    assert loaded == changed
    assert loaded.stops[3].place_id == "shinsegae-centum-city"
    assert loaded.stops[1].locked is True  # 나머지는 그대로


def test_get_missing_plan(store):
    with pytest.raises(PlanNotFoundError) as error:
        store.get_plan("no-such-plan")
    assert error.value.code == "plan_not_found" and error.value.plan_id == "no-such-plan"


def test_update_missing_plan_does_not_create_it(store):
    with pytest.raises(PlanNotFoundError):
        store.update_plan(make_plan("plan-x"))
    with pytest.raises(PlanNotFoundError):
        store.get_plan("plan-x")


def test_create_duplicate_plan_keeps_the_original(store):
    store.create_plan(make_plan())
    other = make_plan().model_copy(update={"date": "2026-12-01"})
    with pytest.raises(PlanAlreadyExistsError):
        store.create_plan(other)
    assert store.get_plan("plan-a").date.isoformat() == "2026-11-21"


def test_changing_objects_outside_does_not_change_stored_plan(store):
    plan = make_plan()
    returned = store.create_plan(plan)
    plan.stops[0].locked = True  # 넘긴 객체를 고쳐도
    returned.stops.clear()  # 돌려받은 객체를 고쳐도
    got = store.get_plan("plan-a")
    got.stops[1].locked = False  # 읽은 객체를 고쳐도

    fresh = store.get_plan("plan-a")
    assert len(fresh.stops) == 4
    assert fresh.stops[0].locked is False and fresh.stops[1].locked is True


# ---- 세션 ----


def test_session_create_then_get(store, clock):
    created = store.create_session(make_profile("ja"))
    assert created.session_id.startswith("sess-") and created.plan_id is None
    assert created.created_at == created.updated_at == START
    assert store.get_session(created.session_id) == created


def test_get_missing_session(store):
    with pytest.raises(SessionNotFoundError) as error:
        store.get_session("sess-none")
    assert error.value.code == "session_not_found"


def test_each_session_gets_its_own_id(store):
    assert store.create_session(make_profile()).session_id != store.create_session(make_profile()).session_id


def test_create_session_with_plan_requires_existing_plan(store):
    with pytest.raises(PlanNotFoundError):
        store.create_session(make_profile(), plan_id="plan-a")
    store.create_plan(make_plan())
    assert store.create_session(make_profile(), plan_id="plan-a").plan_id == "plan-a"


def test_link_plan_to_session(store, clock):
    store.create_plan(make_plan())
    session = store.create_session(make_profile())
    clock.advance(5)

    linked = store.link_plan(session.session_id, "plan-a")

    assert linked.plan_id == "plan-a"
    assert linked.created_at == START and linked.updated_at == START + timedelta(minutes=5)
    assert linked.profile == session.profile
    assert store.get_session(session.session_id) == linked


def test_link_plan_rejects_missing_plan_or_session(store):
    store.create_plan(make_plan())
    session = store.create_session(make_profile())
    with pytest.raises(PlanNotFoundError):
        store.link_plan(session.session_id, "plan-none")
    with pytest.raises(SessionNotFoundError):
        store.link_plan("sess-none", "plan-a")
    assert store.get_session(session.session_id).plan_id is None


def test_get_plan_for_session_returns_only_the_linked_plan(store):
    store.create_plan(make_plan("plan-a"))
    store.create_plan(make_plan("plan-b"))
    session_a = store.create_session(make_profile(), plan_id="plan-a")
    no_plan = store.create_session(make_profile())

    assert store.get_plan_for_session(session_a.session_id, "plan-a").plan_id == "plan-a"
    with pytest.raises(PlanAccessDeniedError) as error:
        store.get_plan_for_session(session_a.session_id, "plan-b")
    assert isinstance(error.value, PlanNotFoundError) and error.value.code == "plan_not_found"
    with pytest.raises(PlanAccessDeniedError):
        store.get_plan_for_session(no_plan.session_id, "plan-a")
    with pytest.raises(SessionNotFoundError):
        store.get_plan_for_session("sess-none", "plan-a")


def test_sessions_do_not_share_state(store):
    store.create_plan(make_plan("plan-a"))
    store.create_plan(make_plan("plan-b"))
    a = store.create_session(make_profile("ja"), plan_id="plan-a")
    b = store.create_session(make_profile("en"))

    store.link_plan(b.session_id, "plan-b")
    returned = store.get_session(a.session_id)
    returned.profile.interests.append("changed")  # 읽은 객체를 고쳐도

    assert store.get_session(a.session_id).plan_id == "plan-a"
    assert store.get_session(a.session_id).profile == make_profile("ja")
    assert store.get_session(b.session_id).plan_id == "plan-b"
    assert store.get_session(b.session_id).profile.language == "en"


# ---- 잘못된 데이터 ----


def test_plan_that_is_not_a_model_is_rejected(store):
    with pytest.raises(InvalidDataError):
        store.create_plan(make_plan().model_dump(mode="json"))


def test_plan_built_without_validation_is_rejected(store):
    broken = Plan.model_construct(plan_id="plan-z", date="not-a-date", profile=make_profile(), stops=[])
    with pytest.raises(InvalidDataError):
        store.create_plan(broken)
    with pytest.raises(PlanNotFoundError):
        store.get_plan("plan-z")


def test_plan_broken_after_creation_is_not_saved(store):
    store.create_plan(make_plan())
    plan = make_plan()
    plan.stops[0].start = "not-a-time"  # 필드 대입은 검증되지 않는다
    with pytest.raises(InvalidDataError):
        store.update_plan(plan)
    assert store.get_plan("plan-a") == make_plan()


@pytest.mark.parametrize("bad_id", ["", "   "])
def test_blank_ids_are_rejected(store, bad_id):
    with pytest.raises(InvalidDataError):
        store.create_plan(make_plan(bad_id))
    with pytest.raises(InvalidDataError):
        store.get_plan(bad_id)
    with pytest.raises(InvalidDataError):
        store.get_session(bad_id)


def test_invalid_profile_is_rejected_without_leaking_the_value(store):
    with pytest.raises(InvalidDataError) as error:
        store.create_session(Profile.model_construct(language="klingon", interests=[], diet=[]))
    assert "profile.language" in str(error.value) or "language" in str(error.value)
    assert "klingon" not in str(error.value)
    with pytest.raises(InvalidDataError):
        store.create_session({"language": "en"})


def test_stored_data_that_no_longer_matches_the_model_is_a_storage_error(store, caplog):
    store.create_plan(make_plan())
    session = store.create_session(make_profile())
    raw_item(store, "PLAN#plan-a")["plan"]["date"] = "not-a-date"
    raw_item(store, f"SESSION#{session.session_id}")["profile"] = {"language": "klingon"}

    with caplog.at_level(logging.ERROR, logger="app.storage.service"):
        with pytest.raises(StorageError):
            store.get_plan("plan-a")
        with pytest.raises(StorageError):
            store.get_session(session.session_id)
    assert "모델과 맞지 않습니다" in caplog.text and "klingon" not in caplog.text


# ---- DynamoDB 백엔드 ----


@pytest.fixture
def table() -> FakeTable:
    return FakeTable()


@pytest.fixture
def dynamo_store(table, clock) -> Storage:
    return Storage(DynamoBackend(table), clock=clock)


def test_dynamodb_items_use_single_table_keys(dynamo_store, table):
    dynamo_store.create_plan(make_plan())
    session = dynamo_store.create_session(make_profile(), plan_id="plan-a")

    plan_item = table.items[("PLAN#plan-a", "META")]
    assert set(plan_item) == {"pk", "sk", "plan", "updated_at"}
    assert plan_item["plan"]["plan_id"] == "plan-a"
    session_item = table.items[(f"SESSION#{session.session_id}", "META")]
    assert set(session_item) == {"pk", "sk", "session_id", "plan_id", "profile", "created_at", "updated_at"}
    assert session_item["plan_id"] == "plan-a"


def test_dynamodb_reads_are_strongly_consistent(dynamo_store, table):
    dynamo_store.create_plan(make_plan())
    dynamo_store.get_plan("plan-a")
    reads = [kwargs for name, kwargs in table.calls if name == "get_item"]
    assert reads and all(kwargs["ConsistentRead"] is True for kwargs in reads)


def test_dynamodb_writes_use_conditions(dynamo_store, table):
    dynamo_store.create_plan(make_plan())
    dynamo_store.update_plan(make_plan())
    session = dynamo_store.create_session(make_profile())
    dynamo_store.link_plan(session.session_id, "plan-a")

    puts = [kwargs["ConditionExpression"] for name, kwargs in table.calls if name == "put_item"]
    assert puts == ["attribute_not_exists(pk)", "attribute_exists(pk)", "attribute_not_exists(pk)"]
    (update,) = [kwargs for name, kwargs in table.calls if name == "update_item"]
    # 속성 이름은 placeholder 로 바꿔 예약어(plan 등)와 겹치지 않게 한다
    assert update["UpdateExpression"] == "SET #a0 = :v0, #a1 = :v1"
    assert update["Names"] == {"#a0": "plan_id", "#a1": "updated_at"}


@pytest.mark.parametrize(
    "failure",
    [
        ClientError({"Error": {"Code": "AccessDeniedException", "Message": "secret-detail"}}, "Op"),
        EndpointConnectionError(endpoint_url="https://dynamodb.invalid"),
    ],
)
def test_dynamodb_failures_become_storage_errors(failure, clock, caplog):
    failing = Storage(DynamoBackend(FakeTable(fail_with=failure)), clock=clock)
    calls = [
        lambda: failing.get_plan("plan-a"),
        lambda: failing.create_plan(make_plan()),
        lambda: failing.update_plan(make_plan()),
        lambda: failing.get_session("sess-a"),
    ]
    with caplog.at_level(logging.ERROR, logger="app.storage.dynamodb"):
        for call in calls:
            with pytest.raises(StorageError) as error:
                call()
            assert not isinstance(error.value, (PlanNotFoundError, SessionNotFoundError))
    assert "DynamoDB" in caplog.text
    assert "plan-a" not in caplog.text and "secret-detail" not in caplog.text  # 키·상세 메시지는 로그에 없다


def test_dynamodb_link_and_session_failures_become_storage_errors(clock):
    store = Storage(DynamoBackend(table := FakeTable()), clock=clock)
    store.create_plan(make_plan())
    session = store.create_session(make_profile())
    table.fail_with = ClientError({"Error": {"Code": "ThrottlingException", "Message": "x"}}, "UpdateItem")
    with pytest.raises(StorageError):
        store.link_plan(session.session_id, "plan-a")


def test_dynamodb_backend_is_built_from_config(monkeypatch):
    created = {}

    class FakeResource:
        def Table(self, name):
            created["table"] = name
            return FakeTable()

    def fake_resource(service, **kwargs):
        created.update(service=service, **kwargs)
        return FakeResource()

    monkeypatch.setattr(dynamodb.boto3, "resource", fake_resource)
    monkeypatch.setattr(config, "DYNAMODB_TABLE", "busan-guide-test")
    monkeypatch.setattr(config, "BEDROCK_REGION", "ap-northeast-2")

    DynamoBackend.from_config()

    assert created["service"] == "dynamodb" and created["table"] == "busan-guide-test"
    assert created["region_name"] == "ap-northeast-2"
    assert created["config"].connect_timeout == 5 and created["config"].read_timeout == 5
    assert created["config"].retries["max_attempts"] == 1


def test_dynamodb_backend_needs_a_table_name(monkeypatch, caplog):
    monkeypatch.setattr(config, "DYNAMODB_TABLE", "")
    with caplog.at_level(logging.ERROR, logger="app.storage.dynamodb"):
        with pytest.raises(StorageError):
            DynamoBackend.from_config()
    assert "DYNAMODB_TABLE" in caplog.text


# ---- 목 모드 (USE_MOCK=1) ----


@pytest.fixture
def no_aws(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("목 모드에서 AWS 에 접근했습니다.")

    monkeypatch.setattr(dynamodb.boto3, "resource", refuse)
    monkeypatch.setattr(dynamodb.boto3, "client", refuse)
    monkeypatch.setattr(config, "DYNAMODB_TABLE", "")


def test_mock_mode_works_without_aws_or_table_name(no_aws):
    plan = storage.create_plan(make_plan("plan-m"))
    session = storage.create_session(make_profile("zh-Hans"))
    storage.link_plan(session.session_id, "plan-m")

    assert storage.get_plan("plan-m") == plan  # 같은 테스트 안에서 저장한 값을 다시 읽는다
    assert storage.get_plan_for_session(session.session_id, "plan-m") == plan
    assert storage.get_session(session.session_id).plan_id == "plan-m"
    assert config.missing_keys() == []


def test_mock_store_has_sample_plan_until_reset(no_aws):
    sample = Plan.model_validate_json(SAMPLE_PLAN_JSON)
    assert storage.get_plan("plan-1") == sample

    storage.update_plan(sample.model_copy(update={"stops": sample.stops[:1]}))
    assert len(storage.get_plan("plan-1").stops) == 1

    storage.reset_mock_store()
    assert storage.get_plan("plan-1") == sample


def test_reset_mock_store_clears_everything(no_aws):
    session = storage.create_session(make_profile())
    storage.create_plan(make_plan("plan-m"))

    storage.reset_mock_store(seed=False)

    with pytest.raises(PlanNotFoundError):
        storage.get_plan("plan-m")
    with pytest.raises(PlanNotFoundError):
        storage.get_plan("plan-1")
    with pytest.raises(SessionNotFoundError):
        storage.get_session(session.session_id)


def test_mock_store_returns_copies(no_aws):
    first = storage.get_plan("plan-1")
    first.stops.clear()
    assert len(storage.get_plan("plan-1").stops) == 4


def test_new_ids_are_unique_and_prefixed():
    assert storage.new_plan_id().startswith("plan-") and storage.new_session_id().startswith("sess-")
    assert len({storage.new_plan_id() for _ in range(100)}) == 100


def test_reset_mock_store_refuses_outside_mock_mode(monkeypatch):
    monkeypatch.setattr(config, "USE_MOCK", False)
    with pytest.raises(RuntimeError):
        storage.reset_mock_store()


def test_non_mock_mode_uses_dynamodb(monkeypatch, table):
    class FakeResource:
        def Table(self, name):
            return table

    monkeypatch.setattr(dynamodb.boto3, "resource", lambda *args, **kwargs: FakeResource())
    monkeypatch.setattr(config, "USE_MOCK", False)
    monkeypatch.setattr(config, "DYNAMODB_TABLE", "busan-guide-test")

    storage.create_plan(make_plan("plan-d"))

    assert ("PLAN#plan-d", "META") in table.items
    with pytest.raises(PlanNotFoundError):
        storage.get_plan("plan-1")  # 목 모드의 샘플 일정은 보이지 않는다


# ---- 설정 ----


def test_missing_keys_requires_table_name_only_outside_mock_mode(monkeypatch):
    monkeypatch.setenv("DATA_GO_KR_KEY_DECODING", "dummy")
    monkeypatch.delenv("DYNAMODB_TABLE", raising=False)

    monkeypatch.setattr(config, "USE_MOCK", False)
    assert config.missing_keys() == ["DYNAMODB_TABLE"]
    monkeypatch.setenv("DYNAMODB_TABLE", "busan-guide-test")
    assert config.missing_keys() == []

    monkeypatch.delenv("DYNAMODB_TABLE")
    monkeypatch.delenv("DATA_GO_KR_KEY_DECODING")
    monkeypatch.setattr(config, "USE_MOCK", True)
    assert config.missing_keys() == []


def test_session_state_ignores_unknown_fields_for_forward_compatibility():
    state = SessionState.model_validate(
        {
            "session_id": "sess-1",
            "plan_id": None,
            "profile": {"language": "en"},
            "created_at": START.isoformat(),
            "updated_at": START.isoformat(),
            "history": ["나중에 추가될 필드"],
        }
    )
    assert state.session_id == "sess-1"
