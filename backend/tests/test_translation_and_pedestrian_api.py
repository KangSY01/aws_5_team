import json
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import Mock

from app import agent
from app import handler as api
from app.models.api import ChatReturnRoutes
from app.tools import pedestrian
from scripts.local_invoke import make_event


def post(path, body):
    response = api.handler(make_event("POST", path, json.dumps(body)))
    return response["statusCode"], json.loads(response["body"])


def test_translation_uses_aws_language_codes(monkeypatch):
    translate = Mock()
    translate.translate_text.return_value = {"TranslatedText": "謝謝"}
    client = Mock(return_value=translate)
    monkeypatch.setattr(api.boto3, "client", client)

    assert post("/translate", {"q": "고마워요", "source": "ko", "target": "zh-Hant"}) == (
        200, {"translatedText": "謝謝"},
    )
    client.assert_called_once_with("translate", region_name=api.config.BEDROCK_REGION)
    translate.translate_text.assert_called_once_with(Text="고마워요", SourceLanguageCode="ko", TargetLanguageCode="zh-TW")


def test_walking_route_returns_only_wgs84_lines(monkeypatch):
    monkeypatch.setenv("TMAP_APP_KEY", "test-key")
    line = [[129.16, 35.16], [129.17, 35.17]]
    features = [
        {"geometry": {"type": "Point", "coordinates": line[0]}},
        {"geometry": {"type": "LineString", "coordinates": line}},
    ]
    call = Mock(return_value=BytesIO(json.dumps({"features": features}).encode()))
    monkeypatch.setattr(pedestrian, "urlopen", call)

    body = {"origin": {"lat": 35.16, "lng": 129.16}, "destination": {"lat": 35.17, "lng": 129.17}}
    assert post("/routes/pedestrian", body) == (200, {"paths": [line]})
    request = call.call_args.args[0]
    assert json.loads(request.data)["resCoordType"] == "WGS84GEO"
    assert json.loads(request.data)["startX"] == 129.16
    monkeypatch.delenv("TMAP_APP_KEY")
    assert post("/routes/pedestrian", body)[0] == 503


def test_chat_exposes_ranked_return_options_with_station_coordinates():
    output = SimpleNamespace(name="get_return_options", data={
        "origin": {"place_id": "haeundae-beach"},
        "destination": {"station": "Seomyeon"},
        "ranked": [{"travel_min": 51, "option": {
            "station": "Dongbaek", "walk_min": 12, "depart_at": "2026-11-28T22:00:00+09:00",
            "time_source": "kakao",
        }}],
    })
    chat = SimpleNamespace(recorder=SimpleNamespace(outputs=[output]))
    result = ChatReturnRoutes.model_validate(agent._return_routes(chat))
    assert result.origin_place_id == "haeundae-beach"
    assert result.options[0].station.names["ko"] == "동백역"
    assert result.options[0].travel_min == 51
