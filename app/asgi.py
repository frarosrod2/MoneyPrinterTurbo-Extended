"""Application implementation - ASGI."""

import os

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger

from app.config import config
from app.models.exception import HttpException
from app.router import root_api_router
from app.utils import utils


def exception_handler(request: Request, e: HttpException):
    return JSONResponse(
        status_code=e.status_code,
        content=utils.get_response(e.status_code, e.data, e.message),
    )


def validation_exception_handler(request: Request, e: RequestValidationError):
    return JSONResponse(
        status_code=400,
        content=utils.get_response(
            status=400, data=e.errors(), message="field required"
        ),
    )


def get_application() -> FastAPI:
    """Initialize FastAPI application.

    Returns:
       FastAPI: Application object instance.

    """
    instance = FastAPI(
        title=config.project_name,
        description=config.project_description,
        version=config.project_version,
        debug=False,
    )
    instance.include_router(root_api_router)
    instance.add_exception_handler(HttpException, exception_handler)
    instance.add_exception_handler(RequestValidationError, validation_exception_handler)
    return instance


app = get_application()

# Configures the CORS middleware for the FastAPI app
cors_allowed_origins_str = os.getenv("CORS_ALLOWED_ORIGINS", "")
origins = cors_allowed_origins_str.split(",") if cors_allowed_origins_str else ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

task_dir = utils.task_dir()


class SafeStaticFiles(StaticFiles):
    """StaticFiles that never crash on Windows path edge cases.

    Starlette's default lookup_path calls os.path.commonpath(), which raises
    ValueError("Paths don't have the same drive") when the requested URL
    resolves to a path on another drive (or contains "\\?\" prefixes),
    turning a harmless 404 into an unhandled ASGI exception.
    """

    def lookup_path(self, path: str):
        for directory in self.all_directories:
            try:
                joined_path = os.path.join(directory, path)
                if self.follow_symlink:
                    full_path = os.path.abspath(joined_path)
                else:
                    full_path = os.path.realpath(joined_path)
                real_directory = os.path.realpath(directory)
                try:
                    common_path = os.path.commonpath([full_path, real_directory])
                except ValueError:
                    # Different drives / mixed relative-absolute: treat as 404.
                    continue
                if os.path.normcase(common_path) != os.path.normcase(real_directory):
                    # Don't allow misbehaving clients to break out of the
                    # static files directory.
                    continue
                try:
                    return full_path, os.stat(full_path)
                except (FileNotFoundError, NotADirectoryError):
                    continue
            except OSError:
                continue
        return "", None


app.mount(
    "/tasks", SafeStaticFiles(directory=task_dir, html=True, follow_symlink=True), name=""
)

public_dir = utils.public_dir()
app.mount("/", SafeStaticFiles(directory=public_dir, html=True), name="")


@app.on_event("shutdown")
def shutdown_event():
    logger.info("shutdown event")


@app.on_event("startup")
def startup_event():
    logger.info("startup event")
