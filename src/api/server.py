"""HTTP API Mini App + раздача статики фронта."""

import datetime as dt
import re

from fastapi import Depends, FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from .. import runtime
from ..data.files import get_all_hobbies, get_hobby_display_name, norm_hobby
from ..utils.dates import date_for_time
from .auth import require_tg_auth

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class EntryRequest(BaseModel):
    date: str
    hobby: str = Field(min_length=1, max_length=64)
    hours: float = Field(ge=0, le=24)

    @field_validator("date")
    @classmethod
    def _date_iso(cls, v: str) -> str:
        if not DATE_RE.match(v):
            raise ValueError("date must be YYYY-MM-DD")
        dt.date.fromisoformat(v)  # ValueError на несуществующую дату
        return v

    @field_validator("hobby")
    @classmethod
    def _hobby_clean(cls, v: str) -> str:
        v = norm_hobby(v)
        if not v or ":" in v:
            raise ValueError("bad hobby key")
        return v


def create_app(serve_static: bool = True) -> FastAPI:
    app = FastAPI(title="Hobby Tracker API")

    @app.get("/api/hobbies")
    async def hobbies(_: dict = Depends(require_tg_auth)):
        return {
            "hobbies": [{"key": h, "display": get_hobby_display_name(h)}
                        for h in get_all_hobbies()],
            "default_date": date_for_time(),
            "queue_pending": runtime.pending_count(),
        }

    @app.get("/api/day/{date}")
    async def day(date: str, _: dict = Depends(require_tg_auth)):
        if not DATE_RE.match(date):
            raise HTTPException(status_code=400, detail="date must be YYYY-MM-DD")
        values = await runtime.get_day_values(date)
        return {"values": values, "queue_pending": runtime.pending_count()}

    @app.post("/api/entry")
    async def entry(req: EntryRequest, _: dict = Depends(require_tg_auth)):
        pending = runtime.record_entry(req.date, req.hobby, req.hours, source="miniapp")
        return {"ok": True, "queue_pending": pending}

    @app.get("/api/queue")
    async def queue(_: dict = Depends(require_tg_auth)):
        """Лёгкий статус очереди — фронт опрашивает после записи, пока не 0"""
        return {"queue_pending": runtime.pending_count()}

    if serve_static:
        app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")
    return app
