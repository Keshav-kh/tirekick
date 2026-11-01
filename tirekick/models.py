"""Shared data contracts between the three workstreams.

Every branch imports from here. Changing a field or enum here is a CONTRACT CHANGE:
open a small PR to `main` that touches only this file + docs/CONTRACTS.md, and tell
the group before merging (see docs/WORKFLOW.md). Adding an optional field with a
default is safe; renaming or removing one breaks the other branches.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------- enums


class Severity(str, Enum):
    GREEN = "green"
    YELLOW = "yellow"
    RED = "red"


class EvidenceType(str, Enum):
    CODE_MISSING = "code_missing"                  # C1
    TAKE_HAS_CUTS = "take_has_cuts"                # C2
    VIN_UNREADABLE = "vin_unreadable"              # C3
    VIN_INVALID = "vin_invalid"                    # C3
    VIN_MISMATCH_DOORS = "vin_mismatch_doors"      # C4
    VIN_LISTING_MISMATCH = "vin_listing_mismatch"  # C5
    RECALL_FOUND = "recall_found"                  # C6
    WARNING_LIGHT_HIDDEN = "warning_light_hidden"  # C7
    WARNING_LIGHT_ON = "warning_light_on"          # C8
    ODOMETER_MISMATCH = "odometer_mismatch"        # C9
    ENGINE_WARM = "engine_warm"                    # C10
    SCREEN_REPLAY = "screen_replay"                # C11
    SCAM_SIGNAL = "scam_signal"                    # C12
    PRICE_BELOW_MARKET = "price_below_market"      # C13
    POSITIVE = "positive"                          # green confirmations ("all lights swept on")


class EvidenceSource(str, Enum):
    VIDEO = "video"
    VIN_DECODE = "vin_decode"
    RECALLS = "recalls"
    CHAT = "chat"
    COMPS = "comps"
    LISTING = "listing"


class LightName(str, Enum):
    CHECK_ENGINE = "check_engine"
    AIRBAG = "airbag"
    ABS = "abs"
    BATTERY = "battery"
    OIL_PRESSURE = "oil_pressure"
    BRAKE = "brake"
    TPMS = "tpms"
    COOLANT_TEMP = "coolant_temp"
    OTHER = "other"


# Lights that must come on at key-on for any 1996+ car (SPEC §6.3 honesty notes).
MUST_LIGHT: frozenset[LightName] = frozenset(
    {LightName.CHECK_ENGINE, LightName.AIRBAG, LightName.ABS}
)
# Lights that are red (not yellow) if they stay on after the engine starts (SPEC C8).
CRITICAL_IF_ON: frozenset[LightName] = frozenset(
    {LightName.CHECK_ENGINE, LightName.AIRBAG, LightName.OIL_PRESSURE, LightName.BRAKE}
)


class ChatRole(str, Enum):
    BUYER = "buyer"
    SELLER = "seller"
    TIREKICK = "tirekick"


class NegotiationStatus(str, Enum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    AGREED = "agreed"
    WALKED_AWAY = "walked_away"


class DealStatus(str, Enum):
    NEW = "new"                          # buyer said hi, no listing yet
    LISTING_PARSED = "listing_parsed"    # listing + ceiling known, join link sent to buyer
    CHALLENGE_SENT = "challenge_sent"    # seller joined, challenge delivered
    PROOF_RECEIVED = "proof_received"    # video downloaded, verification running
    VERIFIED = "verified"                # report ready, verdict GREEN/YELLOW
    REJECTED = "rejected"                # report ready, verdict RED
    NEGOTIATING = "negotiating"
    AGREED = "agreed"
    WALKED_AWAY = "walked_away"
    EXPIRED = "expired"


# --------------------------------------------------------------------------- listing


class Listing(BaseModel):
    listing_id: str
    source: Literal["facebook_marketplace", "dubizzle", "other"] = "other"
    url: str | None = None
    title: str = ""
    asking_price: int
    currency: str = "USD"
    year: int | None = None
    make: str | None = None
    model: str | None = None
    trim: str | None = None
    engine: str | None = None
    mileage: int | None = None
    mileage_unit: Literal["mi", "km"] = "mi"
    vin: str | None = None
    location: str | None = None
    seller_name: str | None = None
    description: str = ""
    raw_text: str = ""


# --------------------------------------------------------------------------- proof take


class ProofChallenge(BaseModel):
    challenge_id: str
    deal_id: str
    code: str = Field(min_length=6, max_length=6)
    issued_at: datetime = Field(default_factory=utcnow)
    expires_at: datetime
    message_text: str  # exact WhatsApp text sent to the seller (SPEC §6.1)


class LightObservation(BaseModel):
    light: LightName
    lit_at_key_on: bool | None = None       # None = couldn't tell
    on_after_start: bool | None = None
    key_on_timestamp_s: float | None = None
    after_start_timestamp_s: float | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class ProofTakeAnalysis(BaseModel):
    """What Muse Spark saw in the seller's proof video. Facts only, no verdicts."""

    video_path: str
    duration_s: float | None = None
    code_read: str | None = None
    code_matches: bool = False
    code_timestamp_s: float | None = None
    continuous_take: bool = False
    cut_timestamps_s: list[float] = Field(default_factory=list)
    screen_replay_suspected: bool = False
    windshield_vin_read: str | None = None
    windshield_vin_timestamp_s: float | None = None
    door_vin_read: str | None = None
    door_vin_timestamp_s: float | None = None
    lights: list[LightObservation] = Field(default_factory=list)
    key_on_timestamp_s: float | None = None
    engine_start_timestamp_s: float | None = None
    odometer_read: int | None = None
    odometer_unit: Literal["mi", "km"] | None = None
    odometer_timestamp_s: float | None = None
    engine_cold: bool | None = None
    temp_gauge_timestamp_s: float | None = None
    model_notes: str = ""
    runs: int = 1                    # how many Muse Spark samples were merged
    agreement: float = 1.0           # fraction of runs that agreed on the light statuses
    raw_outputs: list[dict] = Field(default_factory=list)


# --------------------------------------------------------------------------- deterministic checks


class VinDecode(BaseModel):
    vin: str
    check_digit_valid: bool
    north_american: bool             # first char 1-5; check digit only mandatory if True
    year: int | None = None
    make: str | None = None
    model: str | None = None
    trim: str | None = None
    engine: str | None = None        # e.g. "1.8L 4cyl"
    body: str | None = None
    error_text: str = ""             # vPIC ErrorText, "" when clean


class Recall(BaseModel):
    campaign_number: str
    component: str = ""
    summary: str = ""
    consequence: str = ""
    remedy: str = ""
    report_date: str | None = None


class PriceComps(BaseModel):
    currency: str = "USD"
    low: int | None = None
    median: int | None = None
    high: int | None = None
    n: int = 0
    sources: list[str] = Field(default_factory=list)  # URLs the numbers came from
    note: str = ""


# --------------------------------------------------------------------------- evidence + report


class Evidence(BaseModel):
    id: str                          # "EV-01", unique within one report
    type: EvidenceType
    severity: Severity
    summary: str                     # one line, safe to quote to the seller
    detail: str = ""
    source: EvidenceSource
    verified: bool = True            # only verified evidence may be cited in negotiation
    clip_start_s: float | None = None
    clip_end_s: float | None = None
    frame_path: str | None = None    # still frame for the report card
    highlight_path: str | None = None  # SAM 3.1 overlay (optional)
    price_impact: int = Field(default=0, ge=0)  # suggested deduction, same currency as listing


class VerificationReport(BaseModel):
    deal_id: str
    listing: Listing
    challenge: ProofChallenge
    analysis: ProofTakeAnalysis | None = None
    vin_decode: VinDecode | None = None
    recalls: list[Recall] = Field(default_factory=list)
    comps: PriceComps | None = None
    evidence: list[Evidence] = Field(default_factory=list)
    verdict: Severity
    fair_price_low: int | None = None
    fair_price_high: int | None = None
    inspection_questions: list[str] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=utcnow)

    @staticmethod
    def compute_verdict(evidence: list[Evidence]) -> Severity:
        """Overall verdict is computed in code, never by the model (SPEC §6.3)."""
        severities = {e.severity for e in evidence}
        if Severity.RED in severities:
            return Severity.RED
        if Severity.YELLOW in severities:
            return Severity.YELLOW
        return Severity.GREEN

    def evidence_by_id(self) -> dict[str, Evidence]:
        return {e.id: e for e in self.evidence}


# --------------------------------------------------------------------------- chat + negotiation


class ChatMessage(BaseModel):
    role: ChatRole
    text: str = ""
    media_path: str | None = None    # local path after download
    media_type: str | None = None    # "video/mp4", "image/jpeg", ...
    timestamp: datetime = Field(default_factory=utcnow)
    wa_message_id: str | None = None


class Offer(BaseModel):
    """A draft message to the seller. Must pass negotiate.check_offer before it's shown."""

    amount: int | None               # None only for a walk-away with no number
    cites: list[str] = Field(default_factory=list)  # Evidence ids
    message_text: str
    is_final: bool = False           # "deal at $X" confirmation
    is_walk_away: bool = False


class NegotiationTurn(BaseModel):
    role: ChatRole
    text: str
    amount: int | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=utcnow)


class NegotiationState(BaseModel):
    deal_id: str
    buyer_ceiling: int
    asking_price: int
    currency: str = "USD"
    last_offer: int | None = None
    last_seller_ask: int | None = None
    rounds: int = 0
    max_rounds: int = 4
    turns: list[NegotiationTurn] = Field(default_factory=list)
    status: NegotiationStatus = NegotiationStatus.NOT_STARTED


# --------------------------------------------------------------------------- deal (owned by A)


class Deal(BaseModel):
    deal_id: str                     # "DEAL-4821"; also the seller's join code
    buyer_wa_id: str                 # WhatsApp id (phone number, digits only)
    seller_wa_id: str | None = None
    status: DealStatus = DealStatus.NEW
    listing: Listing | None = None
    buyer_ceiling: int | None = None
    challenge: ProofChallenge | None = None
    report: VerificationReport | None = None
    negotiation: NegotiationState | None = None
    pending_draft: Offer | None = None  # waiting for buyer's 1/2/3
    awaiting_edit: bool = False         # buyer pressed 2/Edit; their next text is the instruction
    chat: list[ChatMessage] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
