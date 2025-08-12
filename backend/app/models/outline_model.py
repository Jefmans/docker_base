# app/models/outline_model.py
from pydantic import BaseModel, Field, validator
from typing import List, Optional

class OutlineSection(BaseModel):
    heading: str
    goals: Optional[str] = None

    # REQUIRED and must be non-empty
    questions: List[str]  # no default!

    # Use default_factory to avoid shared mutable default
    subsections: List["OutlineSection"] = Field(default_factory=list)

    @validator("questions")
    def questions_non_empty(cls, v):
        if not v:
            raise ValueError("questions must be a non-empty list")
        return v

    class Config:
        arbitrary_types_allowed = True

OutlineSection.update_forward_refs()

class Outline(BaseModel):
    title: str
    abstract: str
    sections: List[OutlineSection] = Field(default_factory=list)
