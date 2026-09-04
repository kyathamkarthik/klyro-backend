import os
from dotenv import load_dotenv
from langchain_core.prompts import PromptTemplate
from langchain_openai import ChatOpenAI

load_dotenv()

llm = ChatOpenAI(temperature=0.2, model="gpt-3.5-turbo")

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
analysis_chain = prompt | llm

def analyze_and_correct_payload(integration_flow_name: str, error_message: str, payload: str = None, raw_payload: str = None):
    """
    Invokes the LangChain pipeline to analyze the SAP error and correct the payload.
    Accepts either 'payload' or 'raw_payload' to prevent keyword mismatch errors.
    """
    actual_payload = payload if payload is not None else raw_payload
    
    response = analysis_chain.invoke({
        "iflow_name": integration_flow_name,
        "error_msg": error_message,
        "payload": actual_payload
    })
    
    return response.content