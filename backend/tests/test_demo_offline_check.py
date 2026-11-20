"""오프라인 시연 점검 스크립트의 가드와 표 출력 테스트. 전체 점검은 여기서 실행하지 않는다."""

import socket
from pathlib import Path

import pytest

from scripts import demo_offline_check as check


def test_네트워크_가드는_실제_connect_전에_차단하고_횟수를_센다():
    sock = socket.socket()
    try:
        with check.NetworkGuard() as guard:
            with pytest.raises(check.NetworkBlocked):
                sock.connect(("192.0.2.1", 9))  # 문서용 TEST-NET 주소. patched connect라 실제 연결은 없다.
        assert guard.attempts == 1
    finally:
        sock.close()


def test_결과_표는_성공과_실패를_모두_표시한다(capsys):
    rows = [check.Result("1", "도구", True, "ok"), check.Result("2", "경로", False, "broken")]
    check.print_table(rows)
    output = capsys.readouterr().out
    assert "| 장면" in output and "성공" in output and "실패" in output
    assert "도구" in output and "경로" in output


def test_스크립트는_요청한_handler_경로와_오프라인_스위치를_포함한다():
    source = Path(check.__file__).read_text(encoding="utf-8")
    for path in ('"/plan/check"', 'f"/plan/{plan.plan_id}/delay"', '"/speak"', '"/events"'):
        assert source.count(path) == 1
    assert 'os.environ["USE_MOCK"] = "1"' in source
    assert 'os.environ["FAKE_LLM"] = "1"' in source
    assert "NetworkGuard()" in source
