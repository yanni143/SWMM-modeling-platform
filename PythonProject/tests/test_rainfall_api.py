"""Exercise the HTTP contracts without opening connections or running app startup."""

import asyncio
import json

from fastapi import FastAPI

from Controller.model_routes import router


def request(method, path, payload=None, query=""):
    app = FastAPI()
    app.include_router(router)
    messages = []
    body = json.dumps(payload).encode() if payload is not None else b""

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message):
        messages.append(message)

    asyncio.run(
        app(
            {
                "type": "http",
                "http_version": "1.1",
                "method": method,
                "scheme": "http",
                "path": path,
                "query_string": query.encode(),
                "root_path": "",
                "headers": [(b"content-type", b"application/json")],
                "client": ("127.0.0.1", 1),
                "server": ("127.0.0.1", 80),
            },
            receive,
            send,
        )
    )
    status = next(
        message["status"] for message in messages if message["type"] == "http.response.start"
    )
    data = b"".join(
        message.get("body", b"") for message in messages if message["type"] == "http.response.body"
    )
    return status, json.loads(data)


def test_event_catalog_is_independent_of_model_roots():
    status, events = request("GET", "/api/rainfall-events", query="study_area=JJ")
    assert status == 200 and len(events) == 1
    assert events[0]["total_rainfall_mm"] == 226.2
    assert len(events[0]["values_mm"]) == 576
    assert "baseline_version_id" not in events[0]
    assert request("GET", "/api/rainfall-events", query="study_area=LC") == (200, [])


def test_custom_preview_returns_actual_series_and_rejects_bad_rows():
    payload = {
        "study_area": "LC",
        "simulation_duration_seconds": 3600,
        "rainfall_options": {
            "mode": "custom",
            "start_seconds": 0,
            "time_step_seconds": 300,
            "values_mm": [0, 1.5, 0],
        },
    }
    status, result = request("POST", "/api/rainfall/preview", payload)
    assert status == 200
    assert result["values_mm"] == [0, 1.5, 0]
    assert result["total_rainfall_mm"] == 1.5
    assert result["peak_rainfall_mm_h"] == 18
    assert result["duration_seconds"] == 900
    payload["rainfall_options"]["values_mm"] = [0, -1]
    status, result = request("POST", "/api/rainfall/preview", payload)
    assert status == 422
    assert result["detail"][0]["loc"][-1] == 1


def test_real_preview_requires_explicit_sufficient_simulation_duration():
    payload = {
        "study_area": "JJ",
        "simulation_duration_seconds": 3600,
        "rainfall_options": {"mode": "real", "event_id": "jj_real_20260913_2d"},
    }
    status, result = request("POST", "/api/rainfall/preview", payload)
    assert status == 422 and "超过模拟时长" in result["detail"]
    payload["simulation_duration_seconds"] = 172800
    status, result = request("POST", "/api/rainfall/preview", payload)
    assert status == 200 and result["total_rainfall_mm"] == 226.2
