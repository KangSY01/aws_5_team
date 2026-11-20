import io
import json

from app import config
from app.handler import handler
from app.tools import activities
from scripts.local_invoke import make_event


def test_activity_search_returns_kakao_details(monkeypatch):
    monkeypatch.setattr(config, "KAKAO_REST_API_KEY", "test")

    def provider(request, *, timeout):
        assert "size=5" in request.full_url
        assert request.get_header("Authorization") == "KakaoAK test"
        return io.BytesIO(json.dumps({"documents": [{
            "id": "123", "place_name": "Test Escape Room", "category_name": "Entertainment",
            "address_name": "부산 해운대구", "road_address_name": "부산 해운대구 테스트로 1",
            "phone": "051-000-0000",
        }]}).encode())

    monkeypatch.setattr(activities, "urlopen", provider)
    result = handler(make_event("GET", "/activities", query={"area": "해운대", "kind": "escape_room"}))
    assert result["statusCode"] == 200
    assert json.loads(result["body"])["places"] == [{
        "id": "123", "name": "Test Escape Room", "category": "Entertainment",
        "address": "부산 해운대구 테스트로 1", "phone": "051-000-0000", "url": "https://place.map.kakao.com/123",
    }]
