import os
from dotenv import load_dotenv
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from pydantic import BaseModel, Field
from typing import Literal, Optional
from security_utils import mask_pii

load_dotenv()

class AIDiagnosisOutput(BaseModel):
    root_cause: str = Field(description="Clear explanation of the error")
    failure_type: Literal["SYNTAX", "MAPPING_GROOVY", "SCHEMA_MISMATCH", "BUSINESS_DATA", "INFRASTRUCTURE"]
    risk_level: Literal["LOW", "MEDIUM", "HIGH"]
    confidence_score: float = Field(ge=0.0, le=1.0)
    corrected_payload: Optional[str] = Field(default=None, description="Sanitized fixed payload if resolvable")

diagnosis_prompt = ChatPromptTemplate.from_messages([
    ("system", "You are an enterprise SAP Integration Suite diagnostic engine. Analyze the sanitized MPL trace. Output ONLY valid structured diagnostic schema."),
    ("human", "iFlow: {iflow_name}\nError Context: {error_msg}\nPayload: {payload}")
])

def analyze_and_correct_payload(integration_flow_name: str, error_message: str, payload: str = None, raw_payload: str = None):
    actual_payload = payload if payload is not None else raw_payload
    safe_payload = mask_pii(actual_payload) if actual_payload else ""
    safe_error_msg = mask_pii(error_message) if error_message else ""
    
    # Route complex Groovy or Logic to Claude 3.5 Sonnet; syntax to GPT-4o-mini
    complex_indicators = ['groovy', 'mapping', 'oauth', 'token', 'certificate', 'handshake', 'xslt', 'logic']
    if any(k in safe_error_msg.lower() for k in complex_indicators):
        model_name = "claude-3-5-sonnet-20240620"
        llm = ChatAnthropic(temperature=0.1, model_name=model_name)
    else:
        model_name = "gpt-4o-mini"
        llm = ChatOpenAI(temperature=0.1, model_name=model_name)
        
    structured_llm = llm.with_structured_output(AIDiagnosisOutput, include_raw=True)
    analysis_chain = diagnosis_prompt | structured_llm
    
    response = analysis_chain.invoke({
        "iflow_name": integration_flow_name,
        "error_msg": safe_error_msg,
        "payload": safe_payload
    })
    
    parsed_output = response.get("parsed")
    raw_message = response.get("raw")
    
    input_tokens = output_tokens = 0
    if raw_message:
        usage = getattr(raw_message, "usage_metadata", None)
        if usage:
            input_tokens = usage.get("input_tokens", 0)
            output_tokens = usage.get("output_tokens", 0)
        else:
            fallback_usage = getattr(raw_message, "response_metadata", {}).get("token_usage", {})
            input_tokens = fallback_usage.get("prompt_tokens", 0)
            output_tokens = fallback_usage.get("completion_tokens", 0)
            
    return parsed_output, input_tokens, output_tokens, model_name