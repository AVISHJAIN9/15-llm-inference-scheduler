import pytest
import json
from fastapi.testclient import TestClient
from api.app import app

def test_SCH_100_streaming_inference_api():
    client = TestClient(app)

    payload = {
        "request_id": "test-stream-1",
        "model_name": "gpt-2",
        "prompt": "Tell me a story",
        "max_tokens": 3
    }

    with client.stream("POST", "/api/v1/inference/stream", json=payload) as response:
        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]

        lines = [line.strip() for line in response.iter_lines() if line.strip()]
        # Check event stream lines
        assert len(lines) >= 2
        tokens_received = []

        for line in lines:
            if line.startswith("data: "):
                data_str = line[len("data: "):]
                if data_str == "[DONE]":
                    break
                parsed = json.loads(data_str)
                assert parsed["request_id"] == "test-stream-1"
                assert "token" in parsed
                assert parsed["step"] >= 1
                tokens_received.append(parsed["token"])

        assert len(tokens_received) >= 1
        assert any("tok" in t for t in tokens_received)
