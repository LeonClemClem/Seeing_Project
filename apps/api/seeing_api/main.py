"""FastAPI entrypoint: `uvicorn seeing_api.main:app`."""

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse

from seeing_api.api import router
from seeing_api.auth import router as auth_router
from seeing_api.measurements import router as measurements_router
from seeing_api.places import router as places_router
from seeing_api.schemas import Health

API_CACHE = "private, max-age=300"
ASSET_CACHE = "public, max-age=31536000, immutable"
STATIC_FILE_CACHE = "public, max-age=3600"
INDEX_CACHE = "no-cache"


def create_app(static_dir: str | Path | None = None) -> FastAPI:
    app = FastAPI(title="Seeing the Sky API", version="0.1.0", docs_url="/api/docs", openapi_url="/api/openapi.json")

    @app.middleware("http")
    async def api_cache_headers(request: Request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/api/") and "cache-control" not in response.headers:
            response.headers["Cache-Control"] = API_CACHE if response.status_code < 400 else "no-store"
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        """422 as usual, but auth errors never echo what was submitted (it may be a password)."""
        if not request.url.path.startswith("/api/auth/"):
            return await request_validation_exception_handler(request, exc)
        errors = [{k: v for k, v in e.items() if k not in {"input", "ctx", "url"}} for e in exc.errors()]
        return JSONResponse({"detail": jsonable_encoder(errors)}, status_code=422)

    @app.get("/healthz", response_model=Health)
    def healthz() -> Health:
        return Health(status="ok")

    app.include_router(router)
    app.include_router(auth_router)
    app.include_router(places_router)
    app.include_router(measurements_router)

    root = Path(static_dir if static_dir is not None else os.environ.get("STATIC_DIR", "/app/static"))
    if root.is_dir():
        _mount_spa(app, root.resolve())
    return app


def _mount_spa(app: FastAPI, root: Path) -> None:
    index = root / "index.html"

    @app.api_route("/{path:path}", methods=["GET", "HEAD"], include_in_schema=False)
    def spa(path: str):
        if path == "api" or path.startswith("api/"):
            raise HTTPException(404, "Not Found")
        if path:
            candidate = (root / path).resolve()
            if candidate.is_relative_to(root) and candidate.is_file():
                cache = ASSET_CACHE if path.startswith("assets/") else STATIC_FILE_CACHE
                if candidate == index:
                    cache = INDEX_CACHE
                return FileResponse(candidate, headers={"Cache-Control": cache})
            if path.startswith("assets/"):
                # A missing hashed asset must not be answered with index.html (wrong MIME, cached forever).
                return JSONResponse({"detail": "Not Found"}, status_code=404, headers={"Cache-Control": "no-store"})
        if not index.is_file():
            raise HTTPException(404, "Not Found")
        return FileResponse(index, headers={"Cache-Control": INDEX_CACHE})


app = create_app()
