"""Tests for FastAPI web UI endpoints."""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from scrubmeta.web import create_app


@pytest.fixture
def client() -> TestClient:
    """Create a FastAPI test client."""
    app = create_app()
    return TestClient(app)


@pytest.fixture
def sample_jpeg(tmp_path: Path) -> Path:
    """Create a minimal valid JPEG for testing."""
    from PIL import Image

    img = Image.new("RGB", (10, 10), color="red")
    jpeg_path = tmp_path / "test.jpg"
    img.save(jpeg_path, format="JPEG")
    return jpeg_path


@pytest.fixture
def sample_png(tmp_path: Path) -> Path:
    """Create a minimal valid PNG for testing."""
    from PIL import Image

    img = Image.new("RGB", (10, 10), color="blue")
    png_path = tmp_path / "test.png"
    img.save(png_path, format="PNG")
    return png_path


def test_healthz(client: TestClient) -> None:
    """Test /healthz endpoint returns ok."""
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_root_without_ack(client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that / returns 403 ack-required page when user hasn't acknowledged."""
    # Mock ack_path to return a non-existent path
    from scrubmeta import ack

    monkeypatch.setattr(ack, "ack_path", lambda: tmp_path / "nonexistent" / "ack")

    response = client.get("/")
    assert response.status_code == 403
    assert "First-Run Acknowledgment Required" in response.text
    assert "scrubmeta &lt;any-test-file&gt;" in response.text


def test_root_with_ack(client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that / returns the main UI page when user has acknowledged."""
    # Mock ack to be present
    ack_file = tmp_path / "ack"
    ack_file.write_text("acknowledged\n")

    from scrubmeta import ack

    monkeypatch.setattr(ack, "ack_path", lambda: ack_file)

    response = client.get("/")
    assert response.status_code == 200
    assert "scrubmeta" in response.text
    assert "Drop a file here" in response.text


def test_scrub_jpeg_success(
    client: TestClient, sample_jpeg: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test successful JPEG scrubbing via /api/scrub."""
    # Mock ack to be present
    ack_file = tmp_path / "ack"
    ack_file.write_text("acknowledged\n")

    from scrubmeta import ack

    monkeypatch.setattr(ack, "ack_path", lambda: ack_file)

    with sample_jpeg.open("rb") as f:
        response = client.post(
            "/api/scrub",
            files={"file": ("test.jpg", f, "image/jpeg")},
        )

    assert response.status_code == 200
    data = response.json()
    assert "download_url" in data
    assert data["download_url"].startswith("/download/")
    assert "diff" in data
    assert data["diff"]["replacement_metadata"]["make"] == "Generic"
    assert data["diff"]["replacement_metadata"]["model"] == "Camera"


def test_scrub_png_not_implemented(
    client: TestClient, sample_png: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that PNG scrubbing returns 501 (handler not implemented yet)."""
    # Mock ack to be present
    ack_file = tmp_path / "ack"
    ack_file.write_text("acknowledged\n")

    from scrubmeta import ack

    monkeypatch.setattr(ack, "ack_path", lambda: ack_file)

    with sample_png.open("rb") as f:
        response = client.post(
            "/api/scrub",
            files={"file": ("test.png", f, "image/png")},
        )

    assert response.status_code == 501
    assert "not implemented" in response.json()["detail"].lower()


def test_scrub_unsupported_format(client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that unsupported file formats return HTTP 400."""
    # Mock ack to be present
    ack_file = tmp_path / "ack"
    ack_file.write_text("acknowledged\n")

    from scrubmeta import ack

    monkeypatch.setattr(ack, "ack_path", lambda: ack_file)

    # Create a fake .xyz file
    fake_file = io.BytesIO(b"fake content")

    response = client.post(
        "/api/scrub",
        files={"file": ("test.xyz", fake_file, "application/octet-stream")},
    )

    assert response.status_code == 400
    assert "No handler for extension" in response.json()["detail"]


def test_scrub_not_implemented_handler(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that a 501 is returned when the format handler raises NotImplementedError."""
    # Mock ack to be present
    ack_file = tmp_path / "ack"
    ack_file.write_text("acknowledged\n")

    from scrubmeta import ack

    monkeypatch.setattr(ack, "ack_path", lambda: ack_file)

    # Create a minimal HEIC file (handler is a stub that raises NotImplementedError)
    fake_heic = io.BytesIO(b"fake heic content")

    response = client.post(
        "/api/scrub",
        files={"file": ("test.heic", fake_heic, "image/heic")},
    )

    # The handler stub raises NotImplementedError
    assert response.status_code == 501
    assert "not implemented" in response.json()["detail"].lower()


def test_scrub_c2pa_without_header(
    client: TestClient, sample_jpeg: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that C2PA manifests are refused without X-I-Own-This-Content header."""
    # Mock ack to be present
    ack_file = tmp_path / "ack"
    ack_file.write_text("acknowledged\n")

    from scrubmeta import ack, web

    monkeypatch.setattr(ack, "ack_path", lambda: ack_file)

    # Mock has_c2pa_manifest in the web module to return True
    monkeypatch.setattr(web, "has_c2pa_manifest", lambda _: True)

    with sample_jpeg.open("rb") as f:
        response = client.post(
            "/api/scrub",
            files={"file": ("c2pa.jpg", f, "image/jpeg")},
        )

    assert response.status_code == 409
    assert "C2PA content-credential manifest" in response.json()["detail"]


def test_scrub_c2pa_with_header(
    client: TestClient, sample_jpeg: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that C2PA files are accepted with X-I-Own-This-Content: 1 header."""
    # Mock ack to be present
    ack_file = tmp_path / "ack"
    ack_file.write_text("acknowledged\n")

    from scrubmeta import ack, web

    monkeypatch.setattr(ack, "ack_path", lambda: ack_file)

    # Mock has_c2pa_manifest in the web module to return True
    monkeypatch.setattr(web, "has_c2pa_manifest", lambda _: True)

    with sample_jpeg.open("rb") as f:
        response = client.post(
            "/api/scrub",
            files={"file": ("c2pa.jpg", f, "image/jpeg")},
            headers={"X-I-Own-This-Content": "1"},
        )

    assert response.status_code == 200
    data = response.json()
    assert "download_url" in data


def test_scrub_file_too_large(client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that files over 500 MB are rejected with HTTP 413."""
    # Mock ack to be present
    ack_file = tmp_path / "ack"
    ack_file.write_text("acknowledged\n")

    from scrubmeta import ack

    monkeypatch.setattr(ack, "ack_path", lambda: ack_file)

    # Create a fake large file (simulate by streaming chunks)
    # We'll use a BytesIO that reports a large size
    class LargeFile:
        def __init__(self) -> None:
            self.pos = 0
            self.size = 600 * 1024 * 1024  # 600 MB

        async def read(self, n: int = -1) -> bytes:
            if self.pos >= self.size:
                return b""
            chunk_size = min(n, self.size - self.pos) if n > 0 else self.size - self.pos
            self.pos += chunk_size
            return b"x" * chunk_size

    # Note: TestClient doesn't support streaming uploads in the same way,
    # so we'll test this by checking the logic works with a mock.
    # For now, we'll skip this test in the interest of time and rely on manual testing.
    # A real integration test would require a full ASGI test client with streaming support.

    # Instead, we'll test with a smaller file that exceeds the limit
    # by monkeypatching the MAX_FILE_SIZE constant
    from scrubmeta import web

    original_max = web.MAX_FILE_SIZE
    monkeypatch.setattr(web, "MAX_FILE_SIZE", 100)  # Set to 100 bytes

    # Create a 200-byte file
    large_content = b"x" * 200

    response = client.post(
        "/api/scrub",
        files={"file": ("large.jpg", io.BytesIO(large_content), "image/jpeg")},
    )

    assert response.status_code == 413
    assert "File too large" in response.json()["detail"]

    # Restore
    monkeypatch.setattr(web, "MAX_FILE_SIZE", original_max)


def test_download_file(client: TestClient, sample_jpeg: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test downloading a scrubbed file via /download/<token>."""
    # Mock ack to be present
    ack_file = tmp_path / "ack"
    ack_file.write_text("acknowledged\n")

    from scrubmeta import ack

    monkeypatch.setattr(ack, "ack_path", lambda: ack_file)

    # First, scrub a file to get a download token
    with sample_jpeg.open("rb") as f:
        scrub_response = client.post(
            "/api/scrub",
            files={"file": ("test.jpg", f, "image/jpeg")},
        )

    assert scrub_response.status_code == 200
    download_url = scrub_response.json()["download_url"]

    # Now download the file
    download_response = client.get(download_url)
    assert download_response.status_code == 200
    assert len(download_response.content) > 0

    # Token should be consumed (second download should fail)
    download_response_2 = client.get(download_url)
    assert download_response_2.status_code == 404


def test_download_invalid_token(client: TestClient) -> None:
    """Test that downloading with an invalid token returns 404."""
    response = client.get("/download/invalid-token-12345")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()
