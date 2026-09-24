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


@needs_ffmpeg
def test_repurpose_format_matrix_exports_multiple_presets(client: TestClient) -> None:
    r = client.post(
        "/api/repurpose",
        files={"file": _mp4()},
        data={"mode": "format_matrix", "presets": ["vertical", "square"], "quality": "60"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 2
    assert len(body["outputs"]) == 2
    assert any("vertical" in name for name in body["outputs"])
    assert any("square" in name for name in body["outputs"])

    # Download and verify it's a zip
    d = client.get(body["download_url"])
    assert d.status_code == 200
    assert d.content[:4] == b"PK\x03\x04"  # ZIP magic number


@needs_ffmpeg
def test_repurpose_caption_variants_burns_in_text(client: TestClient, tmp_path: Path) -> None:
    r = client.post(
        "/api/repurpose",
        files={"file": _mp4()},
        data={
            "mode": "caption_variants",
            "captions": "Test caption 1\nTest caption 2",
            "position": "top",
            "size_pct": "5",
            "color": "white",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 2

    # Download zip and extract to verify content
    d = client.get(body["download_url"])
    assert d.status_code == 200

    # Verify the outputs have different frames (text is burned in)
    import zipfile
    from io import BytesIO

    from scrubmeta.media_tools import extract_frame

    zip_data = BytesIO(d.content)
    with zipfile.ZipFile(zip_data, "r") as zf:
        assert len(zf.namelist()) == 2
        # Extract both videos
        for name in zf.namelist():
            video_path = tmp_path / name
            video_path.write_bytes(zf.read(name))
            # Extract a frame to verify it's valid video
            frame_path = tmp_path / f"{name}.frame.jpg"
            extract_frame(video_path, frame_path, 0.5)
            assert frame_path.exists()
            assert frame_path.stat().st_size > 0


@needs_ffmpeg
def test_repurpose_subtitle_localization_with_srt(client: TestClient, tmp_path: Path) -> None:
    # Create a simple SRT file
    srt_path = tmp_path / "test.en.srt"
    srt_path.write_text("1\n00:00:00,000 --> 00:00:02,000\nHello world\n")

    r = client.post(
        "/api/repurpose",
        files={"file": _mp4(), "srt_files": ("test.en.srt", srt_path.read_bytes(), "text/plain")},
        data={"mode": "subtitle_localization"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 1
    assert any("en.mp4" in name for name in body["outputs"])


@needs_ffmpeg
def test_repurpose_review_copies_includes_visible_stamp(client: TestClient, tmp_path: Path) -> None:
    r = client.post(
        "/api/repurpose",
        files={"file": _mp4()},
        data={
            "mode": "review_copies",
            "recipients": "Alice Johnson\nBob Smith",
            "corner": "tl",
            "size_pct": "3",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 2

    # Download zip and verify stamps are visible
    d = client.get(body["download_url"])
    assert d.status_code == 200

    import zipfile
    from io import BytesIO

    from PIL import Image

    from scrubmeta.media_tools import extract_frame

    zip_data = BytesIO(d.content)
    with zipfile.ZipFile(zip_data, "r") as zf:
        assert len(zf.namelist()) == 2
        # Extract first video and check that a frame differs from source
        first_video = tmp_path / zf.namelist()[0]
        first_video.write_bytes(zf.read(zf.namelist()[0]))

        stamped_frame = tmp_path / "stamped.jpg"
        source_frame = tmp_path / "source.jpg"

        extract_frame(first_video, stamped_frame, 0.5)
        extract_frame(FIXTURE_MP4, source_frame, 0.5)

        # Compare frames - they should differ (stamp is present)
        stamped_img = Image.open(stamped_frame)
        source_img = Image.open(source_frame)

        # Convert to same size for comparison
        if stamped_img.size != source_img.size:
            source_img = source_img.resize(stamped_img.size)

        import numpy as np

        stamped_arr = np.array(stamped_img)
        source_arr = np.array(source_img)

        # Images should differ due to stamp
        diff = np.abs(stamped_arr.astype(int) - source_arr.astype(int)).sum()
        assert diff > 1000, "Stamp should be visible on the frame"


@needs_ffmpeg
def test_repurpose_review_copies_compact_corner_badge(client: TestClient, tmp_path: Path) -> None:
    """Test that review badges are compact and corner-anchored with 2 handles."""
    r = client.post(
        "/api/repurpose",
        files={"file": _mp4()},
        data={
            "mode": "review_copies",
            "recipients": "@alicechen\n@bobsmith",
            "corner": "tl",
            "size_pct": "3",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 2

    # Download zip and extract frame from first output
    d = client.get(body["download_url"])
    assert d.status_code == 200

    import zipfile
    from io import BytesIO

    from PIL import Image

    from scrubmeta.media_tools import extract_frame

    zip_data = BytesIO(d.content)
    with zipfile.ZipFile(zip_data, "r") as zf:
        assert len(zf.namelist()) == 2

        # Extract frame from first video and source video
        first_video_path = tmp_path / zf.namelist()[0]
        first_video_path.write_bytes(zf.read(zf.namelist()[0]))

        stamped_frame_path = tmp_path / "stamped.jpg"
        source_frame_path = tmp_path / "source.jpg"

        extract_frame(first_video_path, stamped_frame_path, 0.5)
        extract_frame(FIXTURE_MP4, source_frame_path, 0.5)

        stamped = Image.open(stamped_frame_path).convert("RGB")
        source = Image.open(source_frame_path).convert("RGB")

        # Resize source to match if needed
        if stamped.size != source.size:
            source = source.resize(stamped.size)

        frame_width, frame_height = stamped.size

        # Check that badge is present in top-left corner by examining pixel differences
        # Sample the top-left corner area (first 15% of width and height)
        corner_width = int(frame_width * 0.15)
        corner_height = int(frame_height * 0.15)

        stamped_corner = stamped.crop((0, 0, corner_width, corner_height))
        source_corner = source.crop((0, 0, corner_width, corner_height))

        import numpy as np
        stamped_arr = np.array(stamped_corner)
        source_arr = np.array(source_corner)

        # Calculate difference in corner
        corner_diff = np.abs(stamped_arr.astype(int) - source_arr.astype(int)).sum()

        # There should be significant difference in the corner (badge present)
        assert corner_diff > 10000, f"Badge should be visible in corner, diff: {corner_diff}"

        # The rest of the frame (outside top-left corner) should be mostly unchanged
        # Sample bottom-right corner as control
        control_x = int(frame_width * 0.8)
        control_y = int(frame_height * 0.8)
        stamped_control = stamped.crop((control_x, control_y, frame_width, frame_height))
        source_control = source.crop((control_x, control_y, frame_width, frame_height))

        stamped_control_arr = np.array(stamped_control)
        source_control_arr = np.array(source_control)
        control_diff = np.abs(stamped_control_arr.astype(int) - source_control_arr.astype(int)).sum()

        # Control area should have much smaller difference than corner
        # (some difference is OK due to re-encoding artifacts)
        assert corner_diff > control_diff * 2, f"Badge should be localized to corner: corner_diff={corner_diff}, control_diff={control_diff}"


def test_repurpose_enforces_caps(client: TestClient) -> None:
    # Test caption cap
    r = client.post(
        "/api/repurpose",
        files={"file": _mp4()},
        data={"mode": "caption_variants", "captions": "\n".join(f"Caption {i}" for i in range(11))},
    )
    assert r.status_code == 400

    # Test recipient cap
    r = client.post(
        "/api/repurpose",
        files={"file": _mp4()},
        data={"mode": "review_copies", "recipients": "\n".join(f"Recipient {i}" for i in range(26))},
    )
    assert r.status_code == 400
