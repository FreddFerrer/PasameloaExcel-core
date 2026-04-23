from __future__ import annotations

from pydantic import BaseModel


class SupportSubmissionResponse(BaseModel):
    ticket_id: str
    status: str
    message: str
    forwarded_channel: str
