"""배포한 AgentCore Runtime 을 호출해 스트림을 api-contract 의 SSE 형식으로 출력한다.

런타임은 `data: {"event": "delta", "data": {...}}` 줄을 보낸다. 여기서 그것을
`event: delta` / `data: {...}` 두 줄로 바꿔 보여 준다(브라우저 앞단 어댑터가 할 변환의 확인용).

실행 (infra/ 에서): uv run --no-project --with boto3 --with "botocore[crt]" python scripts/invoke_hello.py <AgentRuntimeArn> [메시지]
"""

import json
import sys
import uuid

import boto3

REGION = "ap-northeast-2"


def main() -> int:
    if len(sys.argv) < 2:
        print("사용법: invoke_hello.py <AgentRuntimeArn> [메시지]", file=sys.stderr)
        return 2
    arn = sys.argv[1]
    message = sys.argv[2] if len(sys.argv) > 2 else "Hello"

    client = boto3.client("bedrock-agentcore", region_name=REGION)
    response = client.invoke_agent_runtime(
        agentRuntimeArn=arn,
        runtimeSessionId=str(uuid.uuid4()),  # 세션 ID는 33자 이상이어야 한다
        payload=json.dumps({"message": message, "profile": {"language": "en"}}).encode(),
    )

    content_type = response.get("contentType", "")
    print(f"# contentType: {content_type}", file=sys.stderr)
    if "text/event-stream" not in content_type:
        print(b"".join(response["response"]).decode("utf-8"))
        return 1

    last_event = None
    for line in response["response"].iter_lines(chunk_size=10):
        if not line:
            continue
        text = line.decode("utf-8")
        if not text.startswith("data: "):
            continue
        item = json.loads(text[6:])
        last_event = item.get("event")
        print(f"event: {last_event}")
        print(f"data: {json.dumps(item.get('data'), ensure_ascii=False)}\n")

    return 0 if last_event == "done" else 1


if __name__ == "__main__":
    sys.exit(main())
