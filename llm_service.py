import os
from dotenv import load_dotenv
from langchain_core.prompts import PromptTemplate
from langchain_openai import ChatOpenAI
from security_utils import mask_pii

load_dotenv()

# Global Prompt Template
analysis_template = """
You are a senior SAP CPI integration developer.
A message failed in the iFlow: {iflow_name}.
The error message received was: {error_msg}

Analyze the following payload and correct the issue based on the error message.
Return only the corrected payload, no markdown formatting or conversational text.

Raw Payload:
{payload}
"""
prompt = PromptTemplate.from_template(analysis_template)

def get_model_for_task(error_message: str) -> str:
    """
    Klyro AI Router: Automatically selects the most cost-effective model 
    based on the complexity of the error to protect gross margins.
    """
    error_lower = error_message.lower()
    
    # Complex reasoning required for advanced failures
    complex_indicators = ['groovy', 'mapping', 'oauth', 'token', 'certificate', 'handshake']
    if any(indicator in error_lower for indicator in complex_indicators):
        return os.getenv("MODEL_COMPLEX", "gpt-4o") 
        
    # Standard reasoning for most high-volume payloads
    return os.getenv("MODEL_STANDARD", "gpt-4o-mini") 

def analyze_and_correct_payload(integration_flow_name: str, error_message: str, payload: str = None, raw_payload: str = None):
    """
    Invokes the LangChain pipeline to analyze the SAP error and correct the payload.
    Returns the corrected payload alongside precise token usage for Klyro Credit billing.
    """
    actual_payload = payload if payload is not None else raw_payload
    
    # CRITICAL SECURITY STEP: Mask PII before AI processing
    safe_payload = mask_pii(actual_payload) if actual_payload else ""
    safe_error_msg = mask_pii(error_message) if error_message else ""
    
    # 1. Route to the appropriate model
    selected_model = get_model_for_task(safe_error_msg)
    
    # 2. Instantiate LLM dynamically (Lowered temperature to 0.1 to prevent hallucinations)
    llm = ChatOpenAI(temperature=0.1, model=selected_model)
    analysis_chain = prompt | llm
    
    # 3. Execute request with masked data
    response = analysis_chain.invoke({
        "iflow_name": integration_flow_name,
        "error_msg": safe_error_msg,
        "payload": safe_payload
    })
    
    # 4. Extract token usage accurately for the billing ledger
    usage = getattr(response, "usage_metadata", None)
    if usage:
        input_tokens = usage.get("input_tokens", 0)
        output_tokens = usage.get("output_tokens", 0)
    else:
        fallback_usage = response.response_metadata.get("token_usage", {})
        input_tokens = fallback_usage.get("prompt_tokens", 0)
        output_tokens = fallback_usage.get("completion_tokens", 0)
        
    return response.content, input_tokens, output_tokens