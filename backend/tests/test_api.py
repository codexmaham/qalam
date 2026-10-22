from fastapi.testclient import TestClient

from qalam.main import create_app

client = TestClient(create_app())


def test_health_and_language_catalogue():
    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    catalogue = client.get("/api/languages")
    assert catalogue.status_code == 200
    body = catalogue.json()
    ids = {item["id"] for item in body["languages"]}
    assert {"en", "ur", "hi", "zh-hans", "ja", "ko", "ar", "th"} <= ids
    assert len(ids) >= 27
    assert {item["id"] for item in body["templates"]} >= {"single-ruled", "four-line", "tianzige"}
    urdu = next(item for item in body["languages"] if item["id"] == "ur")
    assert urdu["direction"] == "rtl"
    assert urdu["font_style"] == "handwriting"


def test_preview_and_pdf_round_trip():
    payload = {
        "text": "Hello from the notebook.\nالعلم نور.",
        "language": "en",
        "template": "four-line",
        "ink": "blue",
        "name": "Noor",
        "date": "19 Oct 2026",
    }
    preview = client.post("/api/preview", json=payload)
    assert preview.status_code == 200
    body = preview.json()
    assert body["page_count"] >= 1
    assert body["pages"][0]
    assert abs(body["width"] / body["height"] - 210 / 297) < 0.02
    pdf = client.post("/api/pdf", json=payload)
    assert pdf.status_code == 200
    assert pdf.headers["content-type"] == "application/pdf"
    assert pdf.content.startswith(b"%PDF")


def test_unknown_language_is_rejected():
    response = client.post("/api/preview", json={"text": "Hi", "language": "nope"})
    assert response.status_code == 400
