"""대화 에이전트 테스트용 스텁. Bedrock 대신 정해 둔 응답을 돌려주는 모델과, 그 응답을 만드는 도우미.

실제 모델 호출·AWS 자격 증명·네트워크가 필요 없다. 스텁은 에이전트가 모델에 넘긴 도구 목록, 시스템 프롬프트,
메시지(도구 결과 포함)를 기록해서 테스트가 확인할 수 있게 한다.
"""

import asyncio
import itertools
import json

from strands.models import Model

_ids = itertools.count(1)


def text_turn(text: str) -> list[dict]:
    """모델이 문장 하나로 답하고 끝내는 응답."""
    return [
        {"messageStart": {"role": "assistant"}},
        {"contentBlockStart": {"start": {}}},
        {"contentBlockDelta": {"delta": {"text": text}}},
        {"contentBlockStop": {}},
        {"messageStop": {"stopReason": "end_turn"}},
    ]


def tool_turn(*calls: tuple[str, dict]) -> list[dict]:
    """모델이 도구를 (여러 개) 부르려는 응답. calls = (도구 이름, 인자 dict)."""
    events = [{"messageStart": {"role": "assistant"}}]
    for name, args in calls:
        events += [
            {"contentBlockStart": {"start": {"toolUse": {"toolUseId": f"tool-{next(_ids)}", "name": name}}}},
            {"contentBlockDelta": {"delta": {"toolUse": {"input": json.dumps(args)}}}},
            {"contentBlockStop": {}},
        ]
    return events + [{"messageStop": {"stopReason": "tool_use"}}]


class ScriptedModel(Model):
    """turns 를 순서대로 돌려주는 모델. 다 쓰면 같은 마지막 응답 대신 문장 하나로 답한다.

    delay: 응답 전에 기다리는 초. error: 호출될 때 던질 예외. repeat_last: 다 쓴 뒤에도 마지막 응답을 되풀이한다
    (도구만 계속 부르는 모델을 흉내 낼 때).
    """

    def __init__(self, turns: list[list[dict]] | None = None, *, delay: float = 0.0, error: Exception | None = None,
                 repeat_last: bool = False):
        self.turns = list(turns or [])
        self.delay, self.error, self.repeat_last = delay, error, repeat_last
        self.requests: list[dict] = []
        self._last: list[dict] | None = None

    def update_config(self, **model_config) -> None:
        pass

    def get_config(self) -> dict:
        return {}

    async def structured_output(self, *args, **kwargs):
        raise NotImplementedError

    async def stream(self, messages, tool_specs=None, system_prompt=None, **kwargs):
        self.requests.append(
            {"messages": list(messages), "tools": [t["name"] for t in tool_specs or []], "system_prompt": system_prompt}
        )
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.error is not None:
            raise self.error
        if self.turns:
            self._last = self.turns.pop(0)
        elif not (self.repeat_last and self._last is not None):
            self._last = text_turn("(script exhausted)")
        for event in self._last:
            yield event

    # ---- 확인용 ----

    @property
    def tool_names(self) -> set[str]:
        """에이전트가 모델에 등록한 도구 이름."""
        return set(self.requests[0]["tools"])

    @property
    def system_prompt(self) -> str:
        return self.requests[0]["system_prompt"]

    def tool_results(self) -> list[tuple[str, str]]:
        """마지막 모델 호출까지 모델이 받은 도구 결과 (status, 본문)."""
        found = []
        for message in self.requests[-1]["messages"]:
            for block in message.get("content", []):
                if "toolResult" in block:
                    result = block["toolResult"]
                    found.append((result["status"], " ".join(c.get("text", "") for c in result["content"])))
        return found
