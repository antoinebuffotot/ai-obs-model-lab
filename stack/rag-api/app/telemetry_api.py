"""GET / POST /api/telemetry : read and change the telemetry type at runtime (shared by the chat and the agent API)."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app import telemetry

router = APIRouter()


class TelemetryRequest(BaseModel):
    type: str


@router.get("/api/telemetry")
async def get_telemetry():
    return {"enabled": telemetry.is_enabled(), "type": telemetry.active_type(), "switchable": telemetry.switchable(),
            "types": list(telemetry.TYPES)}


@router.post("/api/telemetry")
async def set_telemetry(req: TelemetryRequest):
    try:
        telemetry.switch_type(req.type.strip().lower())
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except RuntimeError as exc:
        raise HTTPException(503, str(exc))
    return await get_telemetry()
