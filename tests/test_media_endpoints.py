"""Endpoint tests for the media suite, run against the real local ffmpeg."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from scrubmeta.web import create_app

FIXTURE_MP4 = Path(__file__).parent / "fixtures" / "phone_video.mp4"

needs_ffmpeg = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="ffmpeg/ffprobe not installed",
)


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


def _mp4() -> tuple[str, bytes, str]:
    return ("phone_video.mp4", FIXTURE_MP4.read_bytes(), "video/mp4")


def _png(tmp_path: Path, name: str, color: tuple[int, int, int]) -> tuple[str, bytes, str]:
    p = tmp_path / name
    Image.new("RGB", (24, 24), color).save(p)
    return (name, p.read_bytes(), "image/png")


@needs_ffmpeg
def test_inspect_returns_streams(client: TestClient) -> None:
    r = client.post("/api/inspect", files={"file": _mp4()})
    assert r.status_code == 200
    body = r.json()
    assert body["filename"] == "phone_video.mp4"
    assert any(s["type"] == "video" for s in body["streams"])
    assert body["duration"] is not None


@needs_ffmpeg
def test_convert_to_gif_and_download_once(client: TestClient) -> None:
    r = client.post(
        "/api/convert",
        files={"file": _mp4()},
        data={"target": "gif", "width": "64", "fps": "5"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["output_file"].endswith(".converted.gif")

    d = client.get(body["download_url"])
    assert d.status_code == 200
    assert d.content[:6] in (b"GIF87a", b"GIF89a")

    again = client.get(body["download_url"])
    assert again.status_code == 404


def test_convert_rejects_bad_target(client: TestClient) -> None:
    r = client.post("/api/convert", files={"file": _mp4()}, data={"target": "avi"})
    assert r.status_code == 400


@needs_ffmpeg
def test_edit_trims_and_reports_shorter_duration(client: TestClient) -> None:
    r = client.post(
        "/api/edit",
        files={"file": _mp4()},
        data={"start": "0", "end": "1", "quality": "60"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["inspection"]["duration"] <= 1.5


def test_edit_rejects_inverted_range(client: TestClient) -> None:
    r = client.post("/api/edit", files={"file": _mp4()}, data={"start": "5", "end": "2"})
    assert r.status_code == 422


@needs_ffmpeg
def test_generate_frame_returns_jpeg(client: TestClient) -> None:
    r = client.post("/api/generate/frame", files={"file": _mp4()}, data={"at": "0.5"})
    assert r.status_code == 200
    d = client.get(r.json()["download_url"])
    assert d.status_code == 200
    assert d.content[:2] == b"\xff\xd8"


@needs_ffmpeg
def test_generate_clip(client: TestClient) -> None:
    r = client.post(
        "/api/generate/clip", files={"file": _mp4()}, data={"start": "0", "duration": "1"}
    )
    assert r.status_code == 200
    assert r.json()["output_file"].endswith(".clip.mp4")


def test_export_presets_are_fixed_canvases(client: TestClient) -> None:
    r = client.get("/api/export-presets")
    assert r.status_code == 200
    presets = r.json()
    assert set(presets) == {"vertical", "square", "landscape", "hd"}
    assert presets["vertical"] == {"width": 1080, "height": 1920, "label": "Vertical 9:16"}


@needs_ffmpeg
def test_variation_letterboxes_to_preset(client: TestClient) -> None:
    r = client.post("/api/variations", files={"file": _mp4()}, data={"preset": "square"})
    assert r.status_code == 200
    assert r.json()["preset"] == "square"


def test_variation_rejects_unknown_preset(client: TestClient) -> None:
    r = client.post("/api/variations", files={"file": _mp4()}, data={"preset": "random"})
    assert r.status_code == 422


def test_duplicates_finds_exact_copy(client: TestClient, tmp_path: Path) -> None:
    a = _png(tmp_path, "a.png", (10, 20, 30))
    b = ("b.png", a[1], "image/png")
    c = _png(tmp_path, "c.png", (250, 250, 250))
    r = client.post(
        "/api/duplicates",
        files=[("files", a), ("files", b), ("files", c)],
        data={"threshold": "95"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["files_scanned"] == 3
    exact = [m for m in body["matches"] if m["kind"] == "exact"]
    assert len(exact) == 1
    assert {exact[0]["a"], exact[0]["b"]} == {"a.png", "b.png"}


def test_duplicates_caps_batch_size(client: TestClient, tmp_path: Path) -> None:
    one = _png(tmp_path, "x.png", (0, 0, 0))
    files = [("files", one)] * 101
    r = client.post("/api/duplicates", files=files, data={"threshold": "90"})
    assert r.status_code == 400
