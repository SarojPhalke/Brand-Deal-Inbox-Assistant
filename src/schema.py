from typing import Literal, Optional
from pydantic import BaseModel, Field

Category = Literal["deal_offer", "needs_more_info", "not_a_fit",
                   "scam_or_phishing", "spam"]
NextStep = Literal["accept", "negotiate", "ask_for_details",
                   "decline", "ignore", "report"]

class Deliverable(BaseModel):
    platform: str                 # instagram | youtube
    kind: str                     # reel | story | integration | dedicated_video
    count: int = 1

class EmailAnalysis(BaseModel):
    email_id: str
    category: Category
    confidence: float = Field(ge=0, le=1)
    brand: Optional[str] = None
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    on_behalf_of: Optional[str] = None      # agency case
    deliverables: list[Deliverable] = []
    fee_amount: Optional[float] = None
    currency: Optional[Literal["INR", "USD"]] = None
    payment_type: Optional[Literal["cash", "gifting"]] = None
    gift_value_inr: Optional[float] = None
    deadline: Optional[str] = None          # ISO date
    usage_rights: Optional[str] = None
    category_of_product: Optional[str] = None  # e.g. smartphones, fantasy_sports
    asks_for_payment_from_creator: bool = False
    asks_for_personal_info: bool = False
    contains_ai_instructions: bool = False  # prompt-injection signal
    mentions_attachment: bool = False
    reasoning: str                          # one or two sentences

class RiskFlag(BaseModel):
    code: str                               # e.g. below_rate
    severity: Literal["info", "warn", "block"]
    reason: str                             # plain-language explanation

class Deal(BaseModel):
    deal_id: str
    brand: Optional[str]
    email_ids: list[str]
    category: Category
    latest_terms: EmailAnalysis
    fee_inr: Optional[float]
    rate_card_inr: Optional[float]
    flags: list[RiskFlag]
    next_step: NextStep
    draft_reply: Optional[str] = None