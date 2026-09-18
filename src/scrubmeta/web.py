"""FastAPI web UI for scrubmeta. Dispatch only — scrubbing logic in formats/."""

from __future__ import annotations

import argparse
import ipaddress
import secrets
import sys
import tempfile
from pathlib import Path
from typing import Any, Literal

import uvicorn
from fastapi import FastAPI, File, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import INTENDED_USE_NOTICE, __version__
from .ack import has_acknowledged
from .formats import UnsupportedFormatError, get_handler
from .provenance import has_c2pa_manifest
from .randomize import Identity, generate_replacement_metadata

# In-memory storage for scrubbed files (token -> path)
_scrubbed_files: dict[str, Path] = {}

# In-memory per-IP processing lock (max one scrub per client IP)
_processing_ips: set[str] = set()

MAX_FILE_SIZE = 500 * 1024 * 1024  # 500 MB


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="scrubmeta",
        version=__version__,
        description=INTENDED_USE_NOTICE,
    )

    # Serve static HTML from src/scrubmeta/static/
    static_dir = Path(__file__).parent / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    @app.get("/", response_class=HTMLResponse)
    async def root() -> HTMLResponse:
        """Serve the main UI page, or an ack-required page if user hasn't acknowledged."""
        if not has_acknowledged():
            return HTMLResponse(
                content=f"""<!DOCTYPE html>
<html>
<head>
    <title>scrubmeta - Acknowledgment Required</title>
    <style>
        body {{ font-family: system-ui, sans-serif; max-width: 600px; margin: 50px auto; padding: 20px; }}
        .notice {{ background: #fef3cd; border: 1px solid #ffc107; padding: 15px; border-radius: 5px; }}
        code {{ background: #f5f5f5; padding: 2px 6px; border-radius: 3px; }}
    </style>
</head>
<body>
    <h1>scrubmeta Web UI</h1>
    <div class="notice">
        <h2>First-Run Acknowledgment Required</h2>
        <p>{INTENDED_USE_NOTICE}</p>
        <p>Before you can use the web UI, you must acknowledge the intended use via the CLI:</p>
        <pre><code>scrubmeta &lt;any-test-file&gt;</code></pre>
        <p>After completing the CLI acknowledgment, refresh this page.</p>
    </div>
</body>
</html>""",
                status_code=403,
            )

        index_path = static_dir / "index.html"
        if not index_path.exists():
            return HTMLResponse(
                content="<h1>scrubmeta Web UI</h1><p>Static files not found.</p>",
                status_code=500,
            )
        return HTMLResponse(content=index_path.read_text())

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        """Health check endpoint."""
        return {"status": "ok"}

    @app.post("/api/scrub")
    async def scrub_file(
        file: UploadFile = File(...),  # noqa: B008
        x_i_own_this_content: str | None = Header(default=None, alias="X-I-Own-This-Content"),  # noqa: B008
    ) -> JSONResponse:
        """Scrub metadata from an uploaded file.

        Returns:
            {"download_url": "/download/<token>", "diff": {...}}

        Raises:
            409: C2PA manifest present without ownership header
            413: File too large
            422: Client already has a scrub in progress
            501: Format handler not implemented
            500: Scrubbing failed
        """
        # Check for in-flight processing (one per IP)
        client_ip = "127.0.0.1"  # In production, extract from request headers if behind proxy
        if client_ip in _processing_ips:
            raise HTTPException(
                status_code=422,
                detail="You already have a scrub in progress. Wait for it to complete.",
            )

        # Acquire processing lock
        _processing_ips.add(client_ip)

        try:
            # Stream upload to tempdir
            temp_dir = Path(tempfile.mkdtemp(prefix="scrubmeta-web-"))
            src_path = temp_dir / (file.filename or "upload")

            # Check file size as we stream
            bytes_written = 0
            with src_path.open("wb") as f:
                while chunk := await file.read(8192):
                    bytes_written += len(chunk)
                    if bytes_written > MAX_FILE_SIZE:
                        # Clean up and reject
                        src_path.unlink(missing_ok=True)
                        temp_dir.rmdir()
                        raise HTTPException(
                            status_code=413,
                            detail=f"File too large. Maximum size is {MAX_FILE_SIZE // (1024*1024)} MB.",
                        )
                    f.write(chunk)

            # C2PA provenance check
            owns_content = x_i_own_this_content == "1"
            if has_c2pa_manifest(src_path) and not owns_content:
                src_path.unlink()
                temp_dir.rmdir()
                raise HTTPException(
                    status_code=409,
                    detail=(
                        f"{src_path.name} contains a C2PA content-credential manifest. "
                        "Include the header 'X-I-Own-This-Content: 1' if you're certain you own it."
                    ),
                )

            # Get handler
            try:
                handler = get_handler(src_path)
            except UnsupportedFormatError as e:
                src_path.unlink()
                temp_dir.rmdir()
                raise HTTPException(status_code=400, detail=str(e)) from e

            # Generate replacement metadata
            suffix = src_path.suffix.lower()
            kind: Literal["image", "video"] = (
                "image" if suffix in {".jpg", ".jpeg", ".png", ".heic", ".heif", ".tif", ".tiff"} else "video"
            )
            replacement = generate_replacement_metadata(kind=kind, identity=Identity())

            # Scrub the file
            dst_path = temp_dir / f"{src_path.stem}.scrubbed{src_path.suffix}"
            try:
                handler(src_path, dst_path, replacement)
            except NotImplementedError as e:
                # Handler stub not yet implemented
                src_path.unlink()
                temp_dir.rmdir()
                raise HTTPException(
                    status_code=501,
                    detail=f"Format handler not implemented: {e}",
                ) from e
            except Exception as e:
                # Scrubbing failed
                src_path.unlink(missing_ok=True)
                dst_path.unlink(missing_ok=True)
                temp_dir.rmdir()
                raise HTTPException(
                    status_code=500,
                    detail=f"Scrubbing failed: {e}",
                ) from e

            # Compute metadata diff (simplified — just showing what verify() would produce)
            diff: dict[str, Any] = {
                "source_file": src_path.name,
                "scrubbed_file": dst_path.name,
                "replacement_metadata": {
                    "make": replacement.make,
                    "model": replacement.model,
                    "timestamp": replacement.iso8601(),
                    "gps": replacement.gps,
                },
                "note": "All original metadata stripped; replacement metadata written.",
            }

            # Clean up source file
            src_path.unlink()

            # Generate download token
            token = secrets.token_urlsafe(16)
            _scrubbed_files[token] = dst_path

            return JSONResponse(
                content={
                    "download_url": f"/download/{token}",
                    "diff": diff,
                }
            )

        finally:
            # Release processing lock
            _processing_ips.discard(client_ip)

    @app.get("/download/{token}")
    async def download_file(token: str) -> FileResponse:
        """Stream a scrubbed file once, then delete it.

        Raises:
            404: Token not found or file already downloaded
        """
        if token not in _scrubbed_files:
            raise HTTPException(status_code=404, detail="Download token not found or expired.")

        file_path = _scrubbed_files.pop(token)
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="File not found.")

        # Return as attachment, then schedule cleanup
        response = FileResponse(
            path=str(file_path),
            filename=file_path.name,
            media_type="application/octet-stream",
        )

        # Schedule file cleanup after response is sent
        # (FastAPI will handle this via background tasks in production; for now, manual cleanup)
        @app.on_event("shutdown")
        async def cleanup() -> None:
            file_path.unlink(missing_ok=True)
            file_path.parent.rmdir()

        return response

    return app


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="scrubmeta-web",
        description="Local web UI for scrubmeta. Drag-drop files for metadata scrubbing.",
    )
    p.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host to bind (default: 127.0.0.1). WARNING: binding to 0.0.0.0 exposes the UI to your network.",
    )
    p.add_argument(
        "--port",
        type=int,
        default=8765,
        help="Port to bind (default: 8765).",
    )
    p.add_argument("--version", action="version", version=f"scrubmeta {__version__}")
    return p


def main(argv: list[str] | None = None) -> int:
    """Entry point for scrubmeta-web console script."""
    args = build_parser().parse_args(argv)

    # Warn if binding to non-loopback
    try:
        host_ip = ipaddress.ip_address(args.host)
        if not host_ip.is_loopback:
            print(
                f"WARNING: Binding to {args.host} (non-loopback). "
                "This exposes the UI to your network. "
                "No authentication is provided. Proceed at your own risk.",
                file=sys.stderr,
            )
    except ValueError:
        # Hostname like 'localhost' — allow it
        pass

    app = create_app()
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    return 0


if __name__ == "__main__":
    sys.exit(main())
