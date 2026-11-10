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


def test_root_serves_the_built_page_and_keeps_the_api(tmp_path, monkeypatch):
    index = tmp_path / "index.html"
    index.write_text('<!doctype html><title>Qalam</title><div id="root">notebook</div>', encoding="utf-8")
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "app.js").write_text("/* qalam */", encoding="utf-8")
    monkeypatch.setenv("QALAM_STATIC", str(tmp_path))
    page_client = TestClient(create_app())

    page = page_client.get("/")
    assert page.status_code == 200
    assert page.headers["content-type"].startswith("text/html")
    assert "notebook" in page.text

    health = page_client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"

    script = page_client.get("/assets/app.js")
    assert script.status_code == 200
    assert b"qalam" in script.content

    voice = page_client.get("/voice")
    assert voice.status_code == 200
    assert "notebook" in voice.text

    missing = page_client.get("/assets/missing.js")
    assert missing.status_code == 404

    unknown_api = page_client.get("/api/does-not-exist")
    assert unknown_api.status_code == 404


def test_root_is_json_when_the_frontend_is_not_built(tmp_path, monkeypatch):
    monkeypatch.setenv("QALAM_STATIC", str(tmp_path))
    bare = TestClient(create_app())
    root = bare.get("/")
    assert root.status_code == 200
    body = root.json()
    assert body["name"] == "Qalam"
    assert body["tagline"] == "Speak it. See it handwritten. Print it."
