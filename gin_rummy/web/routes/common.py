"""Shared route helpers."""

from fastapi import HTTPException


def ok(result: dict) -> dict:
    """Session methods report failures as {"error": ...}; turn that into a 400."""
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result
