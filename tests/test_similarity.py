"""Tests for the duplicate finder."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from scrubmeta.similarity import compare_images, visual_similarity


def test_identical_images_are_100_percent(tmp_path: Path) -> None:
    a = tmp_path / "a.png"
    b = tmp_path / "b.png"
    Image.new("RGB", (20, 20), (20, 40, 60)).save(a)
    b.write_bytes(a.read_bytes())

    assert visual_similarity(a, b) == 100.0
    matches = compare_images([a, b], 99)
    assert len(matches) == 1
    assert matches[0]["kind"] == "exact"


def test_resized_copy_is_near_duplicate(tmp_path: Path) -> None:
    a = tmp_path / "a.png"
    b = tmp_path / "b.png"
    im = Image.new("L", (64, 64), 0)
    for x in range(32):
        for y in range(64):
            im.putpixel((x, y), 255)
    im.save(a)
    im.resize((32, 32)).save(b)

    matches = compare_images([a, b], 90)
    assert len(matches) == 1
    assert matches[0]["kind"] == "near"
    assert matches[0]["similarity"] >= 90


def test_threshold_filters(tmp_path: Path) -> None:
    a = tmp_path / "a.png"
    b = tmp_path / "b.png"
    im = Image.new("L", (16, 16), 0)
    im.putpixel((0, 0), 255)
    im.save(a)
    im2 = Image.new("L", (16, 16), 255)
    im2.putpixel((0, 0), 0)
    im2.save(b)

    assert compare_images([a, b], 100) == []


def test_results_sorted_best_first(tmp_path: Path) -> None:
    base = Image.new("L", (32, 32), 0)
    for x in range(16):
        for y in range(32):
            base.putpixel((x, y), 255)
    a = tmp_path / "a.png"
    b = tmp_path / "b.png"
    c = tmp_path / "c.png"
    base.save(a)
    base.save(b)  # exact copy
    noisy = base.copy()
    for y in range(32):
        noisy.putpixel((16, y), 255)  # shift the edge one column
    noisy.save(c)

    matches = compare_images([a, b, c], 0)
    assert matches[0]["kind"] == "exact"
    assert matches[0]["similarity"] == 100.0
    assert all(
        matches[i]["similarity"] >= matches[i + 1]["similarity"] for i in range(len(matches) - 1)
    )
