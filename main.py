import time
import os
import asyncio
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Dict, Any
from supabase import create_client

from schemas import (
    TenantConnectRequest,
    TenantStatusResponse,
    FailedLogRequest,
    DiagnosticsResponse,
    RetriggerRequest
)
from llm_service import analyze_and_correct_payload
from sap_connector import SAPIntegrationConnector, sap_client

app = FastAPI(
    title="Klyro AI API Engine",
    description="Enterprise API engine handling SAP tenant connections and autonomous recovery.",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://klyroai.in",
        "https://*.pages.dev",
        "http://localhost:5173",
        "http://localhost:3000"
    ],
    allow_origin_regex=r"https://.*\.emergent\.com",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

active_tenants: Dict[str, SAPIntegrationConnector] = {}

@app.on_event("startup")
async def startup_event():
    from automation_worker import run_autonomous_agent
    asyncio.create_task(asyncio.to_thread(run_autonomous_agent))

@app.get("/")
@app.head("/")
def health_check():
    return {"status": "online", "system": "Klyro AI Kernel"}
    
def clean_url(url: str) -> str:
    """Bulletproof sanitization for URLs to prevent DNS [Errno -2] failures."""
    if not url:
        return ""
    # Remove hidden Zero-Width Spaces (\u200b) and standard whitespace
    url = url.strip().strip("\u200b")
    # Fix double protocols if accidentally pasted
    url = url.replace("https://https://", "https://")
    url = url.replace("http://http://", "http://")
    # Ensure scheme exists
    if not url.startswith("http"):
        url = f"https://{url}"
    # Strip trailing slashes so paths append correctly
    return url.rstrip("/")

def clean_secret(secret: str) -> str:
    """Strips hidden unicode characters from IDs and passwords."""
    if not secret:
        return ""
    return secret.strip().strip("\u200b")

@app.post("/api/v1/connect-tenant", response_model=TenantStatusResponse)
def connect_tenant(creds: TenantConnectRequest):
    start_time = time.time()
    
    # Safely unpack and sanitize all inputs before touching SAP
    api_url = clean_url(creds.api_base_url)
    token_url = clean_url(creds.token_url)
    client_id = clean_secret(creds.client_id)
    client_secret = clean_secret(creds.client_secret)
    
    # Fallback to standard client ID/Secret if runtime inputs are empty
    rt_url = clean_url(creds.runtime_url) if creds.runtime_url else ""
    rt_client_id = clean_secret(creds.runtime_client_id) if creds.runtime_client_id else client_id
    rt_secret = clean_secret(creds.runtime_client_secret) if creds.runtime_client_secret else client_secret

    # 1. Test SAP Connection
    try:
        tenant_connector = SAPIntegrationConnector(
            api_base_url=api_url,
            api_client_id=client_id,
            api_client_secret=client_secret,
            token_url=token_url,
            runtime_url=rt_url,
            runtime_client_id=rt_client_id,
            runtime_client_secret=rt_secret
        )
        tenant_connector.test_connection()
        active_tenants[clean_secret(creds.tenant_id)] = tenant_connector
    except Exception as e:
        # We catch the exact SAP failure here
        raise HTTPException(status_code=400, detail=f"SAP Auth Error: {str(e)}")
        
    # 2. Push to Supabase Vault
    try:
        supabase_url = os.getenv("SUPABASE_URL")
        supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        
        if supabase_url and supabase_key:
            supabase = create_client(clean_url(supabase_url), clean_secret(supabase_key))
            supabase.rpc("store_tenant_credentials", {
                "p_tenant_id": clean_secret(creds.tenant_id),
                "p_client_id": client_id,
                "p_client_secret": client_secret,
                "p_runtime_client_id": rt_client_id,
                "p_runtime_client_secret": rt_secret,
                "p_api_base_url": api_url,         # Added for production
                "p_token_url": token_url,          # Added for production
                "p_runtime_url": rt_url            # Added for production
            }).execute()
    except Exception as e:
        # We catch the exact Database failure here
        raise HTTPException(status_code=500, detail=f"Supabase Vault Error: {str(e)}")

    latency = int((time.time() - start_time) * 1000)
    
    # Extract just the hostname to look professional in the dashboard UI
    node_name = rt_url.replace("https://", "").split("/")[0] if rt_url else "active.cfapps.hana.ondemand.com"

    return TenantStatusResponse(
        connected=True,
        tenant_id=clean_secret(creds.tenant_id),
        runtime_node=node_name,
        latency_ms=latency
    )

@app.get("/api/v1/fetch-logs", response_model=List[Dict[str, Any]])
def get_sap_logs(tenant_id: str = None):
    connector = active_tenants.get(tenant_id, sap_client)
    try:
        return connector.fetch_failed_logs()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch logs: {str(e)}")

@app.post("/api/v1/analyze-log", response_model=DiagnosticsResponse)
def analyze_sap_log(request: FailedLogRequest):
    try:
        diagnosis, input_tokens, output_tokens, model_used = analyze_and_correct_payload(
            integration_flow_name=request.integration_flow_name,
            error_message=request.error_message,
            payload=request.raw_payload
        )
        
        fixed_payload = diagnosis.corrected_payload if diagnosis and diagnosis.corrected_payload else "Manual review required."
        confidence = diagnosis.confidence_score if diagnosis else 0.0
        
        return DiagnosticsResponse(
            log_id=request.log_id,
            root_cause_explanation=f"Diagnosis via {model_used}. Action: {diagnosis.failure_type if diagnosis else 'Unknown'}",
            corrected_payload=fixed_payload,
            confidence_score=confidence
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analysis failure: {str(e)}")

@app.post("/api/v1/retrigger-sap")
def retrigger_sap_flow(request: RetriggerRequest, tenant_id: str = None):
    connector = active_tenants.get(tenant_id, sap_client)
    try:
        return connector.retrigger_message(request.runtime_url, request.fixed_payload)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrigger iFlow: {str(e)}")