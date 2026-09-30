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
def health_check():
    return {"status": "online", "system": "Klyro AI Kernel"}

@app.post("/api/v1/connect-tenant", response_model=TenantStatusResponse)
def connect_tenant(creds: TenantConnectRequest):
    start_time = time.time()
    try:
        # 1. Test the SAP connection first
        tenant_connector = SAPIntegrationConnector(
            api_base_url=creds.api_base_url,
            api_client_id=creds.client_id,
            api_client_secret=creds.client_secret,
            token_url=creds.token_url,
            runtime_url=creds.runtime_url,
            runtime_client_id=creds.runtime_client_id,
            runtime_client_secret=creds.runtime_client_secret
        )
        
        tenant_connector.test_connection()
        active_tenants[creds.tenant_id] = tenant_connector
        
        # 2. Securely push the secrets to Supabase Vault via RPC
        supabase_url = os.getenv("SUPABASE_URL")
        supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        
        if supabase_url and supabase_key:
            supabase = create_client(supabase_url, supabase_key)
            supabase.rpc("store_tenant_credentials", {
                "p_tenant_id": creds.tenant_id,
                "p_client_id": creds.client_id,
                "p_client_secret": creds.client_secret,
                "p_runtime_client_id": creds.runtime_client_id,
                "p_runtime_client_secret": creds.runtime_client_secret
            }).execute()

        latency = int((time.time() - start_time) * 1000)

        return TenantStatusResponse(
            connected=True,
            tenant_id=creds.tenant_id,
            runtime_node="active.cfapps.hana.ondemand.com",
            latency_ms=latency
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"SAP Tenant Authentication Failed: {str(e)}")

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