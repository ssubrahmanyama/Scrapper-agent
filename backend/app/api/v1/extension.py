"""
api/v1/extension.py — Browser Extension API endpoints.

Endpoints:
  POST /extension/analyse  — Lightweight PII check for browser extension
  GET  /extension/status   — Auth status check

AppSec notes:
  - Input text limited to 10,000 chars (enforced by Pydantic).
  - Only regex + quick NLP (no full ML pipeline) to stay fast.
  - Rate limited separately: 60 requests/hour per user.
"""
from __future__ import annotations

from pydantic import BaseModel, Field, HttpUrl
from fastapi import APIRouter, Depends
from app.api.v1.deps import get_current_user
from app.models import User
from app.services.nlp.pii_detector import PIIDetector, ExposureScorer

router = APIRouter(prefix="/extension", tags=["Browser Extension"])

_quick_detector = PIIDetector(confidence_threshold=0.80)
_scorer = ExposureScorer()


class AnalyseRequest(BaseModel):
    page_text: str = Field(max_length=10_000)
    page_url: str = Field(max_length=2048)
    domain: str = Field(max_length=253)


class AnalyseResponse(BaseModel):
    pii_count: int
    risk_level: str
    domain: str
    has_exposure: bool


@router.post("/analyse", response_model=AnalyseResponse)
async def analyse_page(
    payload: AnalyseRequest,
    current_user: User = Depends(get_current_user),
):
    """
    Quick PII check for a page. Uses regex layer only (fast, < 50ms).
    Full ML scan available via POST /scans.
    """
    # Regex scan only — no blocking ML inference in extension path
    matches = _quick_detector._regex_scan(payload.page_text, payload.page_url)
    score, risk = _scorer.score(matches)

    return AnalyseResponse(
        pii_count=len(matches),
        risk_level=risk,
        domain=payload.domain,
        has_exposure=len(matches) > 0,
    )


@router.get("/status")
async def extension_status(current_user: User = Depends(get_current_user)):
    """Auth status check for the browser extension."""
    return {
        "authenticated": True,
        "user_email": current_user.email,
        "subscription_tier": current_user.subscription_tier,
    }
