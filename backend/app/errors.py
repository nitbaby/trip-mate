from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class ApiError(Exception):
    def __init__(self, code: str, message: str, status: int = 400, retryable: bool = False):
        self.code, self.message, self.status, self.retryable = code, message, status, retryable


def _body(code, message, retryable=False):
    return {"error": {"code": code, "message": message, "retryable": retryable}}


def install(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api(_: Request, e: ApiError):
        return JSONResponse(_body(e.code, e.message, e.retryable), status_code=e.status)

    @app.exception_handler(RequestValidationError)
    async def _val(_: Request, e: RequestValidationError):
        return JSONResponse(_body("VALIDATION_FAILED", str(e.errors()[:3])), status_code=422)


def not_found(what: str) -> ApiError:
    return ApiError("NOT_FOUND", f"{what} not found", 404)
