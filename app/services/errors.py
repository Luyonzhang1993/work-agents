from typing import Optional


class ServiceUnavailableError(RuntimeError):
    def __init__(self, message: str, cause: Optional[Exception] = None) -> None:
        super().__init__(message)
        self.cause = cause
