"""TMAP pedestrian geometry. Coordinates in the public response are [longitude, latitude]."""

import json
import os
from urllib.request import Request, urlopen

from pydantic import BaseModel, Field


class RoutePoint(BaseModel):
    lat: float = Field(ge=33, le=39)
    lng: float = Field(ge=124, le=132)


class PedestrianRequest(BaseModel):
    origin: RoutePoint
    destination: RoutePoint


class PedestrianResponse(BaseModel):
    paths: list[list[tuple[float, float]]]


def get_pedestrian_route(route: PedestrianRequest) -> PedestrianResponse | None:
    key = os.environ.get("TMAP_APP_KEY")
    if not key:
        return None
    body = {
        "startX": route.origin.lng, "startY": route.origin.lat,
        "endX": route.destination.lng, "endY": route.destination.lat,
        "startName": "출발", "endName": "도착",
        "reqCoordType": "WGS84GEO", "resCoordType": "WGS84GEO",
    }
    request = Request(
        "https://apis.openapi.sk.com/tmap/routes/pedestrian?version=1",
        data=json.dumps(body).encode("utf-8"),
        headers={"appKey": key, "Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=5) as response:
        data = json.load(response)
    paths = [
        feature["geometry"]["coordinates"] for feature in data["features"]
        if feature["geometry"]["type"] == "LineString" and len(feature["geometry"]["coordinates"]) >= 2
    ]
    return PedestrianResponse(paths=paths) if paths else None
