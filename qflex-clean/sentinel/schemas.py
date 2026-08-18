# sentinel/schemas.py
from pydantic import BaseModel, Field, validator
from typing import Optional, Literal

class ThreatModel(BaseModel):
    threat_id: str
    threat_type: str
    severity: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    source_ip: Optional[str]
    confidence_score: float = Field(ge=0.0, le=1.0)
    description: str
    recommended_action: str

    @validator("confidence_score", pre=True)
    def clamp_confidence(cls, v):
        try:
            val = float(v)
            return max(0.0, min(val, 1.0))
        except (ValueError, TypeError):
            return 0.0

class IngressMetrics(BaseModel):
    source_id: str
    reputation: float
    cryptographic_signature: str
    rate_tier: Literal["GUEST", "NODE", "ROOT"]
