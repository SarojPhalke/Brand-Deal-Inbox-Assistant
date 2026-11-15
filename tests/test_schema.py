import pytest
from pydantic import ValidationError
from src.schema import EmailAnalysis

def test_valid_email_analysis():
    a = EmailAnalysis(
        email_id="E-02", category="deal_offer", confidence=0.9,
        fee_amount=100000, currency="INR", payment_type="cash",
        reasoning="Revised offer from Dew Lab.",
    )
    assert a.fee_amount == 100000

def test_bad_category_rejected():
    with pytest.raises(ValidationError):
        EmailAnalysis(email_id="E-X", category="scammy",
                      confidence=0.5, reasoning="x")

def test_confidence_out_of_range_rejected():
    with pytest.raises(ValidationError):
        EmailAnalysis(email_id="E-X", category="spam",
                      confidence=1.7, reasoning="x")