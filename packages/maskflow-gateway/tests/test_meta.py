from fastapi.testclient import TestClient


def test_healthz(client: TestClient) -> None:
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_readyz_ok_with_in_process_store(client: TestClient) -> None:
    r = client.get("/readyz")
    assert r.status_code == 200
    assert r.json()["status"] == "ready"


def test_metrics_is_prometheus_text(client: TestClient) -> None:
    r = client.get("/metrics")
    assert r.status_code == 200
    assert "maskflow_requests_total" in r.text


def test_entities_lists_registered_types(client: TestClient) -> None:
    r = client.get("/v1/entities")
    body = r.json()
    assert r.status_code == 200
    assert "AADHAAR" in body["entities"]
    assert "EMAIL" in body["entities"]
    assert body["count"] == len(body["entities"])
