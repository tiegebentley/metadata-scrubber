"""Media-suite endpoints for the scrubmeta web app.

Registered onto the FastAPI app by web.create_app(). Kept in a separate
module so web.py stays a thin scrub-only dispatcher and the media utilities
(convert, inspect, edit, clip/frame, export presets, duplicate finder) live
in one place. Each endpoint streams the upload to a temp dir, calls the
matching function in media_tools / variations / similarity, and hands the
result back through the same one-time /download/{token} mechanism the scrub
endpoint uses.
"""

from __future__ import annotations

import secrets
import shutil
import tempfile
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from .media_tools import MediaToolError, convert, extract_frame, make_clip, probe, trim_video
from .similarity import compare_images
from .variations import PRESETS, export_variation

MAX_DUPLICATE_FILES = 100


def _write_upload(upload: UploadFile, dest: Path, limit: int, running_total: int = 0) -> int:
    """Stream `upload` to `dest`, enforcing `limit` bytes across the call."""
    total = running_total
    with dest.open("wb") as handle:
        while chunk := upload.file.read(1024 * 1024):
            total += len(chunk)
            if total > limit:
                raise HTTPException(status_code=413, detail="File too large. Maximum size is 500 MB.")
            handle.write(chunk)
    return total


def register_media_endpoints(
    app: FastAPI,
    downloads: dict[str, Path],
    max_file_size: int,
) -> None:
    """Attach the media-suite endpoints to `app`."""

    def save_upload(upload: UploadFile) -> tuple[Path, Path]:
        temp_dir = Path(tempfile.mkdtemp(prefix="scrubmeta-media-"))
        src = temp_dir / Path(upload.filename or "upload").name
        try:
            _write_upload(upload, src, max_file_size)
        except Exception:
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise
        return temp_dir, src

    def register_download(path: Path) -> str:
        token = secrets.token_urlsafe(16)
        downloads[token] = path
        return f"/download/{token}"

    def fail(temp_dir: Path, status: int, detail: str) -> HTTPException:
        shutil.rmtree(temp_dir, ignore_errors=True)
        return HTTPException(status_code=status, detail=detail)

    @app.post("/api/inspect")
    async def inspect_file(file: UploadFile = File(...)) -> JSONResponse:  # noqa: B008
        temp_dir, src = save_upload(file)
        try:
            return JSONResponse(content=probe(src))
        except MediaToolError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    @app.post("/api/convert")
    async def convert_file(
        file: UploadFile = File(...),  # noqa: B008
        target: str = Form(...),  # noqa: B008
        quality: int = Form(90),  # noqa: B008
        fps: int | None = Form(None),  # noqa: B008
        width: int | None = Form(None),  # noqa: B008
        height: int | None = Form(None),  # noqa: B008
    ) -> JSONResponse:
        temp_dir, src = save_upload(file)
        ext = {"gif": ".gif", "mp4": ".mp4", "jpg": ".jpg", "jpeg": ".jpg"}.get(target.lower())
        if not ext:
            raise fail(temp_dir, 400, "Target must be gif, mp4, or jpg.")
        dst = temp_dir / f"{src.stem}.converted{ext}"
        try:
            convert(src, dst, target.lower(), quality, fps, width, height)
        except MediaToolError as exc:
            raise fail(temp_dir, 422, str(exc)) from exc
        src.unlink(missing_ok=True)
        return JSONResponse(content={
            "download_url": register_download(dst),
            "output_file": dst.name,
            "inspection": probe(dst),
        })

    @app.post("/api/edit")
    async def edit_file(
        file: UploadFile = File(...),  # noqa: B008
        start: float = Form(0),  # noqa: B008
        end: float | None = Form(None),  # noqa: B008
        quality: int = Form(90),  # noqa: B008
        speed: float = Form(1.0),  # noqa: B008
    ) -> JSONResponse:
        temp_dir, src = save_upload(file)
        dst = temp_dir / f"{src.stem}.edited.mp4"
        try:
            trim_video(src, dst, start, end, quality, speed)
        except MediaToolError as exc:
            raise fail(temp_dir, 422, str(exc)) from exc
        src.unlink(missing_ok=True)
        return JSONResponse(content={
            "download_url": register_download(dst),
            "output_file": dst.name,
            "inspection": probe(dst),
        })

    @app.post("/api/generate/frame")
    async def generate_frame(
        file: UploadFile = File(...),  # noqa: B008
        at: float = Form(0),  # noqa: B008
    ) -> JSONResponse:
        temp_dir, src = save_upload(file)
        dst = temp_dir / f"{src.stem}.frame.jpg"
        try:
            extract_frame(src, dst, at)
        except MediaToolError as exc:
            raise fail(temp_dir, 422, str(exc)) from exc
        src.unlink(missing_ok=True)
        return JSONResponse(content={"download_url": register_download(dst), "output_file": dst.name})

    @app.post("/api/generate/clip")
    async def generate_clip(
        file: UploadFile = File(...),  # noqa: B008
        start: float = Form(0),  # noqa: B008
        duration: float = Form(10),  # noqa: B008
    ) -> JSONResponse:
        temp_dir, src = save_upload(file)
        dst = temp_dir / f"{src.stem}.clip.mp4"
        try:
            make_clip(src, dst, start, duration)
        except MediaToolError as exc:
            raise fail(temp_dir, 422, str(exc)) from exc
        src.unlink(missing_ok=True)
        return JSONResponse(content={
            "download_url": register_download(dst),
            "output_file": dst.name,
            "inspection": probe(dst),
        })

    @app.get("/api/export-presets")
    async def export_presets() -> JSONResponse:
        return JSONResponse(content=PRESETS)

    @app.post("/api/variations")
    async def create_variation(
        file: UploadFile = File(...),  # noqa: B008
        preset: str = Form(...),  # noqa: B008
        quality: int = Form(90),  # noqa: B008
        fps: int | None = Form(None),  # noqa: B008
    ) -> JSONResponse:
        temp_dir, src = save_upload(file)
        dst = temp_dir / f"{src.stem}.{preset}.mp4"
        try:
            export_variation(src, dst, preset, quality, fps)
        except MediaToolError as exc:
            raise fail(temp_dir, 422, str(exc)) from exc
        src.unlink(missing_ok=True)
        return JSONResponse(content={
            "download_url": register_download(dst),
            "output_file": dst.name,
            "preset": preset,
        })

    @app.post("/api/duplicates")
    async def find_duplicates(
        files: list[UploadFile] = File(...),  # noqa: B008
        threshold: float = Form(90),  # noqa: B008
    ) -> JSONResponse:
        if len(files) > MAX_DUPLICATE_FILES:
            raise HTTPException(
                status_code=400,
                detail=f"Select at most {MAX_DUPLICATE_FILES} images per scan.",
            )
        temp_dir = Path(tempfile.mkdtemp(prefix="scrubmeta-dupes-"))
        paths: list[Path] = []
        total = 0
        try:
            for i, upload in enumerate(files):
                path = temp_dir / Path(upload.filename or f"image-{i}").name
                total = _write_upload(upload, path, max_file_size, total)
                paths.append(path)
            try:
                matches: list[dict[str, Any]] = [dict(m) for m in compare_images(paths, threshold)]
            except Exception as exc:
                raise HTTPException(
                    status_code=422, detail=f"Unable to compare selected images: {exc}"
                ) from exc
            return JSONResponse(content={
                "threshold": threshold,
                "files_scanned": len(paths),
                "matches": matches,
            })
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
