import os
import time
from supabase import create_client
from classifier_service import classify_failure, FailureCategory
from llm_service import analyze_and_correct_payload
from policy_engine import evaluate_recovery_policy
from billing_service import calculate_klyro_credits_from_ai_cost

supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") 
supabase = create_client(supabase_url, supabase_key) if supabase_url and supabase_key else None

retry_cache = {}
MAX_RETRIES = 3

def run_autonomous_agent():
    from main import active_tenants
    print("🤖 Starting Multi-Tenant SAP Agent (Enterprise Architecture)...")
    
    while True:
        if not active_tenants:
            time.sleep(30)
            continue
            
        for tenant_id, sap_client in active_tenants.items():
            failed_logs = sap_client.fetch_failed_logs()
            if not failed_logs: continue

            user_id = None
            if supabase:
                tenant_data = supabase.table("tenant_configs").select("user_id").eq("tenant_id", tenant_id).execute()
                if tenant_data.data:
                    user_id = tenant_data.data[0]["user_id"]
                    wallet = supabase.table("credit_wallets").select("current_balance").eq("user_id", user_id).execute()
                    current_balance = float(wallet.data[0]["current_balance"]) if wallet.data else 0.0
                    if current_balance <= 0.20:
                        break 
            
            for log in failed_logs:
                failed_iflow = log['integration_flow_name']
                log_id = log['log_id']
                error_msg = log['error_message']

                broken_payload = sap_client.fetch_payload_attachment(log_id) or ""
                retry_count = retry_cache.get(log_id, 0)

                # 1. Classification
                category, _ = classify_failure(error_msg)
                
                # 2. AI Diagnosis
                diagnosis = None
                input_tokens = output_tokens = 0
                model_used = "circuit_breaker"
                
                if category != FailureCategory.HARD_STOP:
                    try:
                        diagnosis, input_tokens, output_tokens, model_used = analyze_and_correct_payload(
                            integration_flow_name=failed_iflow,
                            error_message=error_msg,
                            raw_payload=broken_payload
                        )
                    except Exception as e:
                        print(f"❌ AI Diagnosis failed: {str(e)}")
                        continue

                # 3. Policy Execution
                decision = evaluate_recovery_policy(category, diagnosis, retry_count, MAX_RETRIES)
                verification_status = "PENDING"
                
                if decision == "AUTO_RECOVERY" and diagnosis and diagnosis.corrected_payload:
                    res = sap_client.retrigger_message(sap_client.base_runtime_url, diagnosis.corrected_payload)
                    time.sleep(5)
                    verification_status = "SUCCESS" if res.get("status") == "success" else "FAILED"
                    retry_cache.pop(log_id, None)

                elif decision == "APPROVAL":
                    supabase.table("hitl_queue").insert({
                        "tenant_id": tenant_id, "log_id": log_id, "iflow_name": failed_iflow,
                        "error_message": error_msg, "original_payload": broken_payload,
                        "proposed_payload": diagnosis.corrected_payload if diagnosis else "",
                        "status": "pending_approval"
                    }).execute()
                    retry_cache.pop(log_id, None)

                elif decision == "ESCALATION":
                    retry_cache.pop(log_id, None) # Stop infinite loops
                else:
                    retry_cache[log_id] = retry_count + 1
                
                # 4. Immutable Audit
                if supabase:
                    supabase.table("audit_logs").insert({
                        "tenant_id": tenant_id, "log_id": log_id, "iflow_name": failed_iflow,
                        "failure_category": category.value, "decision": decision,
                        "verification_status": verification_status, "ai_model_used": model_used,
                        "tokens_consumed": input_tokens + output_tokens,
                        "details": diagnosis.dict() if diagnosis else {"error": error_msg}
                    }).execute()
                    
                    # 5. Billing
                    if user_id and input_tokens > 0:
                        in_rate = 0.000003 if "claude" in model_used else 0.00000015
                        out_rate = 0.000015 if "claude" in model_used else 0.00000060
                        actual_cost = (input_tokens * in_rate) + (output_tokens * out_rate)
                        
                        credits_to_deduct = calculate_klyro_credits_from_ai_cost(actual_cost, 4.00, 15.0)
                        supabase.rpc("process_ai_deduction", {
                            "p_user_id": user_id, "p_credits_deducted": credits_to_deduct,
                            "p_feature": decision, "p_model": model_used,
                            "p_input_tokens": input_tokens, "p_output_tokens": output_tokens,
                            "p_actual_cost": actual_cost
                        }).execute()
                        
        time.sleep(60)

if __name__ == "__main__":
    run_autonomous_agent()