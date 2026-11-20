"""DynamoDB 백엔드 (USE_MOCK=0). boto3 기본 자격 증명 체인을 쓰고, 키 값은 코드에 두지 않는다.

테이블은 파티션 키 pk(문자열), 정렬 키 sk(문자열)를 가진 단일 테이블이다. 테이블 생성은 infra/ 에서 한다.
읽기는 항상 강한 일관성(ConsistentRead)으로 하고, 쓰기는 조건식으로 있음/없음을 확인한다.
"""

import logging
from typing import Any

import boto3
from botocore.config import Config as BotocoreConfig
from botocore.exceptions import BotoCoreError, ClientError

from app import config
from app.storage.backends import SORT_KEY, ItemExists, ItemMissing, make_item
from app.storage.errors import StorageError

logger = logging.getLogger(__name__)

TIMEOUT_SEC = 5  # team.md: 외부 호출 타임아웃 5초, 재시도 1회
RETRIES = 1  # botocore max_attempts 는 최초 호출을 뺀 재시도 횟수

_CONDITION_FAILED = "ConditionalCheckFailedException"


class DynamoBackend:
    def __init__(self, table: Any):
        """table: boto3 Table 리소스 (get_item, put_item, update_item 을 가진 객체)."""
        self._table = table

    @classmethod
    def from_config(cls) -> "DynamoBackend":
        if not config.DYNAMODB_TABLE:
            logger.error("DYNAMODB_TABLE 환경 변수가 비어 있어 DynamoDB 저장소를 만들 수 없습니다.")
            raise StorageError("DYNAMODB_TABLE 이 설정되지 않았습니다.")
        resource = boto3.resource(
            "dynamodb",
            region_name=config.BEDROCK_REGION,  # AWS_REGION 값. 리소스는 모두 같은 리전에 둔다
            config=BotocoreConfig(
                connect_timeout=TIMEOUT_SEC,
                read_timeout=TIMEOUT_SEC,
                retries={"max_attempts": RETRIES, "mode": "standard"},
            ),
        )
        return cls(resource.Table(config.DYNAMODB_TABLE))

    def get(self, pk: str) -> dict[str, Any] | None:
        try:
            response = self._table.get_item(Key={"pk": pk, "sk": SORT_KEY}, ConsistentRead=True)
        except (ClientError, BotoCoreError) as error:
            raise _storage_error("조회", error) from error
        return response.get("Item")

    def create(self, pk: str, attrs: dict[str, Any]) -> None:
        try:
            self._table.put_item(Item=make_item(pk, attrs), ConditionExpression="attribute_not_exists(pk)")
        except ClientError as error:
            if _condition_failed(error):
                raise ItemExists(pk) from error
            raise _storage_error("생성", error) from error
        except BotoCoreError as error:
            raise _storage_error("생성", error) from error

    def replace(self, pk: str, attrs: dict[str, Any]) -> None:
        try:
            self._table.put_item(Item=make_item(pk, attrs), ConditionExpression="attribute_exists(pk)")
        except ClientError as error:
            if _condition_failed(error):
                raise ItemMissing(pk) from error
            raise _storage_error("수정", error) from error
        except BotoCoreError as error:
            raise _storage_error("수정", error) from error

    def update(self, pk: str, values: dict[str, Any]) -> None:
        names = {f"#a{i}": name for i, name in enumerate(values)}
        expression = "SET " + ", ".join(f"#a{i} = :v{i}" for i in range(len(values)))
        try:
            self._table.update_item(
                Key={"pk": pk, "sk": SORT_KEY},
                UpdateExpression=expression,
                ExpressionAttributeNames=names,  # plan 등 예약어와 겹치지 않게 이름을 치환한다
                ExpressionAttributeValues={f":v{i}": value for i, value in enumerate(values.values())},
                ConditionExpression="attribute_exists(pk)",
            )
        except ClientError as error:
            if _condition_failed(error):
                raise ItemMissing(pk) from error
            raise _storage_error("수정", error) from error
        except BotoCoreError as error:
            raise _storage_error("수정", error) from error


def _condition_failed(error: ClientError) -> bool:
    return error.response.get("Error", {}).get("Code") == _CONDITION_FAILED


def _storage_error(action: str, error: Exception) -> StorageError:
    """키·저장 값은 로그에 넣지 않고 동작과 오류 종류만 남긴다."""
    kind = error.response.get("Error", {}).get("Code", "") if isinstance(error, ClientError) else ""
    logger.error("DynamoDB %s 실패: %s %s", action, type(error).__name__, kind)
    return StorageError("저장소 오류가 발생했습니다.")
