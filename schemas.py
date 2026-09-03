from pydantic import BaseModel, Field
from typing import Optional

class TenantConnectRequest(BaseModel):
    tenant_id: str = Field(..., example="klyro-prd-it-cpi012")
    client_id: str = Field(...)
    client_secret: str = Field(...)
    token_url: str = Field(...)
    api_base_url: str = Field(...)
    runtime_url: Optional[str] = None
    runtime_client_id: Optional[str] = None
    runtime_client_secret: Optional[str] = None

class TenantStatusResponse(BaseModel):
    connected: bool
    tenant_id: str
    runtime_node: str
    latency_ms: int

class FailedLogRequest(BaseModel):
    log_id: str
    integration_flow_name: str
    error_message: str
    raw_payload: str

class DiagnosticsResponse(BaseModel):
    log_id: str
    root_cause_explanation: str
    corrected_payload: str
    confidence_score: float

class RetriggerRequest(BaseModel):
    runtime_url: str
    fixed_payload: str