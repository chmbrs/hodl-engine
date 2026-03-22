from datetime import datetime

from pydantic import BaseModel


class ChatMessage(BaseModel):
    message: str


class AnalysisResponse(BaseModel):
    analysis: str


class AllocationSuggestionRequest(BaseModel):
    market_context: str = ""


class SaveAnalysisRequest(BaseModel):
    label: str
    content: str


class AnalysisSnapshot(BaseModel):
    id: int
    label: str
    content: str
    created_at: datetime
