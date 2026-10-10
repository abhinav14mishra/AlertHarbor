"""Stable REST Endpoint response contract."""


def success(body: dict) -> dict:
    return {"result": "success", **body}


def failure(message: str, code: str = "invalid_request") -> dict:
    return {"result": "failure", "code": code, "message": message}
