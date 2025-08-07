from pydantic import BaseModel
from typing import List, Optional


# from app.models.research_tree import ResearchTree, ResearchNode, Chunk


class OutlineSection(BaseModel):
    heading: str
    goals: Optional[str] = None
    questions: List[str] = []
    subsections: List["OutlineSection"] = []

    class Config:
        arbitrary_types_allowed = True

OutlineSection.update_forward_refs()



class Outline(BaseModel):
    title: str
    abstract: str
    sections: List[OutlineSection]