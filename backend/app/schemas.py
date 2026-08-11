from pydantic import BaseModel
from typing import List


class UploadResponse(BaseModel):
    doc_id: str
    text_excerpt: str


class AskRequest(BaseModel):
    doc_id: str
    question: str


class AskResponse(BaseModel):
    answer: str
    model: str
    history: List[str]
