"""Structured error handling. Never hide failures."""
from fastapi import Request
from fastapi.responses import JSONResponse

async def app_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={
            "error": "internal_error",
            "detail": str(exc),
            "path": str(request.url.path),
        },
    )
