from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class PageCapture(BaseModel):
    url: str
    content: str
    metadata: dict


class OpenTab(BaseModel):
    tab_id: int
    window_id: int
    url: str
    title: str


class SearchQuery(BaseModel):
    query: str
    limit: Optional[int] = 10
    open_tabs: Optional[List[OpenTab]] = None  # For tab switching


class TabSwitchQuery(BaseModel):
    query: str
    open_tabs: List[OpenTab]


class PageResult(BaseModel):
    id: str
    url: str
    title: Optional[str]
    domain: str
    snippet: Optional[str]
    similarity: float
    time_spent: Optional[int]
    captured_at: datetime


class TabSwitchResult(BaseModel):
    tab_id: int
    window_id: int
    url: str
    title: str
    confidence: float


class SearchResponse(BaseModel):
    query_type: str  # "semantic_search" or "tab_switch"
    results: Optional[List[PageResult]] = None
    matched_tab: Optional[TabSwitchResult] = None
