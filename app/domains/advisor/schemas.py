from pydantic import BaseModel


class ChatMessage(BaseModel):
    message: str


class AnalysisResponse(BaseModel):
    analysis: str
