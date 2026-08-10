from fastapi import Request
from fastapi.exceptions import HTTPException, RequestValidationError
from fastapi.responses import JSONResponse


class HttpErrors:
    def __init__(self):
        self.http_exception_type = HTTPException
        self.validation_exception_type = RequestValidationError
        pass

    @staticmethod
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content={
                "error": 1,
                "message": "ValidationError"
            },
        )

    # добавлять новые исключения таким же образом и пробрасывать в main.py


httpErrors = HttpErrors()
