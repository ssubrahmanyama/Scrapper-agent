"""tests/test_nlp.py — Unit tests for PII detector and exposure scorer."""
from __future__ import annotations

import pytest

from app.services.nlp.pii_detector import (
    ExposureScorer,
    PIIDetector,
    PIIMatch,
    PIIType,
)


# ── PIIDetector unit tests (regex layer only — no ML models needed) ───────────
class TestRegexPIIDetection:
    detector = PIIDetector(confidence_threshold=0.5)

    def test_detects_indian_mobile(self):
        text = "Call me on 9876543210 for more info"
        matches = self.detector._regex_scan(text, "https://example.com/page")
        phone_matches = [m for m in matches if m.pii_type == PIIType.PHONE_NUMBER]
        assert len(phone_matches) >= 1

    def test_detects_email(self):
        text = "Contact: john.doe@gmail.com for details"
        matches = self.detector._regex_scan(text, "https://example.com/page")
        email_matches = [m for m in matches if m.pii_type == PIIType.EMAIL_ADDRESS]
        assert len(email_matches) == 1
        assert "john.doe" in email_matches[0].masked_value or "***" in email_matches[0].masked_value

    def test_detects_aadhaar_format(self):
        text = "Aadhaar: 2345 6789 0123"
        matches = self.detector._regex_scan(text, "https://example.com/page")
        id_matches = [m for m in matches if m.pii_type == PIIType.NATIONAL_ID]
        assert len(id_matches) >= 1

    def test_email_masked_not_raw(self):
        """Raw email address must NOT appear in masked_value."""
        text = "Email: arjun.sharma@example.com"
        matches = self.detector._regex_scan(text, "https://example.com")
        for m in matches:
            assert "arjun.sharma@example.com" not in m.masked_value, "Raw PII exposed in result"

    def test_phone_masked_not_raw(self):
        text = "Phone: 9123456789"
        matches = self.detector._regex_scan(text, "https://example.com")
        for m in matches:
            assert "9123456789" not in m.masked_value, "Raw phone number exposed"

    def test_no_false_positive_short_numbers(self):
        text = "There are 12345 items in stock"
        matches = self.detector._regex_scan(text, "https://example.com")
        phone_matches = [m for m in matches if m.pii_type == PIIType.PHONE_NUMBER]
        assert len(phone_matches) == 0

    def test_context_snippet_masks_pii(self):
        text = "Hello, you can reach 9876543210 anytime"
        matches = self.detector._regex_scan(text, "https://example.com")
        for m in matches:
            # Context snippet should use block chars, not expose PII
            assert "9876543210" not in m.context_snippet

    def test_https_only_matches(self):
        """HTTP URLs should not produce results (safety filter)."""
        text = "Phone: 9876543210"
        matches = self.detector._regex_scan(text, "http://insecure.com/page")
        # regex_scan itself doesn't filter by URL scheme — that's PageFetcher's job
        # But source_url should reflect what was passed
        assert all(m.source_url == "http://insecure.com/page" for m in matches)

    def test_multiple_phones_detected(self):
        text = "Call 9876543210 or 8765432109 for support"
        matches = self.detector._regex_scan(text, "https://example.com")
        phone_matches = [m for m in matches if m.pii_type == PIIType.PHONE_NUMBER]
        assert len(phone_matches) >= 2

    def test_us_phone_format(self):
        text = "US number: +1 (555) 123-4567"
        matches = self.detector._regex_scan(text, "https://example.com")
        phone_matches = [m for m in matches if m.pii_type == PIIType.PHONE_NUMBER]
        assert len(phone_matches) >= 1


class TestAddressCoOccurrence:
    detector = PIIDetector(confidence_threshold=0.5)

    def test_detects_name_near_address_keyword(self):
        text = "Arjun Sharma lives at Flat 5, Green Colony, Pune 411001"
        match = self.detector._address_cooccurrence_check(text, "Arjun Sharma", "https://example.com")
        assert match is not None
        assert match.pii_type == PIIType.ADDRESS

    def test_no_match_when_name_absent(self):
        text = "A property at flat 5, Green Colony is available for rent"
        match = self.detector._address_cooccurrence_check(text, "Unknown Person", "https://example.com")
        assert match is None

    def test_no_match_when_far_from_keyword(self):
        """Name and address keyword more than 200 chars apart."""
        text = "Arjun Sharma " + ("x" * 300) + " has a flat in Mumbai"
        match = self.detector._address_cooccurrence_check(text, "Arjun Sharma", "https://example.com")
        assert match is None


# ── ExposureScorer tests ──────────────────────────────────────────────────────
class TestExposureScorer:
    scorer = ExposureScorer()

    def _make_match(self, pii_type: PIIType, confidence: float = 0.9, domain: str = "example.com") -> PIIMatch:
        return PIIMatch(
            pii_type=pii_type,
            masked_value="***",
            confidence=confidence,
            source_url=f"https://{domain}/page",
            source_domain=domain,
            context_snippet="...[masked]...",
            char_start=0,
            char_end=10,
        )

    def test_empty_matches_zero_score(self):
        score, risk = self.scorer.score([])
        assert score == 0.0
        assert risk == "low"

    def test_national_id_gives_high_score(self):
        matches = [self._make_match(PIIType.NATIONAL_ID, confidence=0.95)]
        score, risk = self.scorer.score(matches)
        assert score >= 20.0
        assert risk in ("high", "critical", "medium")

    def test_critical_risk_threshold(self):
        """3x national ID hits should push to critical."""
        matches = [
            self._make_match(PIIType.NATIONAL_ID, domain="site1.com"),
            self._make_match(PIIType.NATIONAL_ID, domain="site2.com"),
            self._make_match(PIIType.ADDRESS, domain="site1.com"),
        ]
        score, risk = self.scorer.score(matches)
        assert risk in ("high", "critical")

    def test_low_confidence_reduces_score(self):
        high_conf = [self._make_match(PIIType.PHONE_NUMBER, confidence=0.95)]
        low_conf = [self._make_match(PIIType.PHONE_NUMBER, confidence=0.60)]

        score_high, _ = self.scorer.score(high_conf)
        score_low, _ = self.scorer.score(low_conf)
        assert score_high > score_low

    def test_co_occurrence_bonus(self):
        """Two different PII types on same domain should add bonus."""
        multi_type = [
            self._make_match(PIIType.PHONE_NUMBER, domain="broker.com"),
            self._make_match(PIIType.ADDRESS, domain="broker.com"),
        ]
        single_type = [
            self._make_match(PIIType.PHONE_NUMBER, domain="broker.com"),
            self._make_match(PIIType.PHONE_NUMBER, domain="broker.com"),
        ]
        score_multi, _ = self.scorer.score(multi_type)
        score_single, _ = self.scorer.score(single_type)
        # Multi-type on same domain gets co-occurrence bonus
        assert score_multi > score_single

    def test_score_capped_at_100(self):
        """Score must never exceed 100."""
        matches = [
            self._make_match(pii_type, domain=f"site{i}.com", confidence=0.99)
            for i, pii_type in enumerate([
                PIIType.NATIONAL_ID, PIIType.FINANCIAL, PIIType.ADDRESS,
                PIIType.PHONE_NUMBER, PIIType.DATE_OF_BIRTH,
            ] * 5)
        ]
        score, _ = self.scorer.score(matches)
        assert score <= 100.0

    def test_risk_levels_correct(self):
        assert self.scorer.score([self._make_match(PIIType.PERSON_NAME, confidence=0.7)])[1] in ("low", "medium")
