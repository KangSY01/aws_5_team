import json
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from pydantic import BaseModel

from app import config

ACTIVITIES = {
    "board_game": "보드게임카페",
    "escape_room": "방탈출",
    "animal_cafe": "동물카페",
    "scenic_cafe": "분위기 좋은 카페",
}
AREAS = {"부산", "해운대", "광안리", "서면", "전포", "남포", "영도", "기장", "송정", "센텀", "부산역"}


class ActivityPlace(BaseModel):
    id: str
    name: str
    category: str
    address: str
    phone: str
    url: str


class ActivitiesResponse(BaseModel):
    places: list[ActivityPlace]


def find_activities(area: str, kind: str) -> list[dict]:
    query = urlencode({"query": f"{area if area == '부산' else '부산 ' + area} {ACTIVITIES[kind]}", "size": 5})
    request = Request(
        f"https://dapi.kakao.com/v2/local/search/keyword.json?{query}",
        headers={"Authorization": f"KakaoAK {config.KAKAO_REST_API_KEY}"},
    )
    with urlopen(request, timeout=5) as response:
        documents = json.load(response)["documents"]

    return [
        {
            "id": str(row["id"]),
            "name": row["place_name"],
            "category": row["category_name"],
            "address": row.get("road_address_name") or row["address_name"],
            "phone": row.get("phone", ""),
            "url": f"https://place.map.kakao.com/{row['id']}",
        }
        for row in documents
        if row.get("place_name") and str(row.get("id", "")).isdigit()
        and row.get("address_name", "").startswith("부산 ")
    ]
