import os
import time
from supabase import create_client
from llm_service import analyze_and_correct_payload
from billing_service import calculate_klyro_credits_from_ai_cost

supabase_url = os.getenv("SUPABASE_URL")
# CRITICAL: Using the service_role key to bypass Row Level Security for background tasks
supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") 
supabase = create_client(supabase_url, supabase_key) if supabase_url and supabase_key else None

retry_cache = {}
MAX_RETRIES = 3

def flag_for_human_review(tenant_id: str, log_id: str, iflow_name: str, error_msg: str, original: str, fixed: str):
    """
    Klyro Trust Mode: Freezes autonomous execution and pushes the AI's proposed 
    payload correction to the HITL database queue for manual approval.
    """
    if not supabase:
        print("⚠️ Supabase client missing. Cannot queue for HITL.")
        return
        
    queue_data = {
        "tenant_id": tenant_id,
        "log_id": log_id,
        "iflow_name": iflow_name,
        "error_message": error_msg,
        "original_payload": original,
        "proposed_payload": fixed,
        "status": "pending_approval"
    }
    
    supabase.table("hitl_queue").insert(queue_data).execute()
    print(f"⚠️ Escalated {log_id} to HITL Dashboard for approval.")

def run_autonomous_agent():
    from main import active_tenants
    print("🤖 Starting 24/7 Multi-Tenant SAP CPI Agent (Trust Mode Enabled)...")
    
    while True:
        if not active_tenants:
            time.sleep(30)
            continue
            
        for tenant_id, sap_client in active_tenants.items():
            try:
                failed_logs = sap_client.fetch_failed_logs()
            except Exception as e:
                print(f"Failed to poll tenant {tenant_id}: {e}")
                continue
                
            if not failed_logs:
                continue

            # Identity & Enterprise Billing Verification
            user_id = None
            if supabase:
                try:
                    tenant_data = supabase.table("tenant_configs").select("user_id").eq("tenant_id", tenant_id).execute()
                    if tenant_data.data:
                        user_id = tenant_data.data[0]["user_id"]
                        
                        wallet = supabase.table("credit_wallets").select("current_balance").eq("user_id", user_id).execute()
                        current_balance = float(wallet.data[0]["current_balance"]) if wallet.data else 0.0
                        
                        if current_balance <= 0.20:
                            print(f"🛑 [BILLING] Tenant {tenant_id} lacks sufficient Klyro Recovery Credits. Parking in HITL.")
                            break 
                except Exception as e:
                    print(f"❌ Could not verify billing for {tenant_id}: {e}")
            
            for log in failed_logs:
                failed_iflow = log['integration_flow_name']
                log_id = log['log_id']
                error_msg = log['error_message']
                
                print(f"⚠️ [Tenant: {tenant_id}] Failure in iFlow: {failed_iflow} (ID: {log_id})")

                broken_payload = sap_client.fetch_payload_attachment(log_id)
                if not broken_payload:
                    continue

                current_retries = retry_cache.get(log_id, 0)
                if current_retries >= MAX_RETRIES:
                    print(f"🛑 [CIRCUIT BREAKER] Escalating Log ID {log_id} to HITL dashboard.")
                    continue 
                
                business_keywords = ['not found', 'out of stock', 'customer', 'material', 'business logic', 'reject']
                if any(keyword in error_msg.lower() for keyword in business_keywords):
                    retry_cache[log_id] = MAX_RETRIES
                    continue
                
                retry_cache[log_id] = current_retries + 1
                
                try:
                    # Semantic Correction
                    raw_fixed_payload, input_tokens, output_tokens = analyze_and_correct_payload(
                        integration_flow_name=failed_iflow,
                        error_message=error_msg,
                        raw_payload=broken_payload
                    )
                    fixed_payload = raw_fixed_payload.replace("```xml", "").replace("```json", "").replace("```", "").strip()
                    
                    # PHASE 2: Freeze execution and flag for manual human review
                    flag_for_human_review(
                        tenant_id=tenant_id,
                        log_id=log_id,
                        iflow_name=failed_iflow,
                        error_msg=error_msg,
                        original=broken_payload,
                        fixed=fixed_payload
                    )
                    
                    # Remove from retry cache since it is safely in the HITL queue
                    retry_cache.pop(log_id, None)
                    
                    # Calculate Actual AI Cost and Deduct Klyro Credits atomically for the analysis
                    if supabase and user_id:
                        actual_cost = (input_tokens * 0.00000015) + (output_tokens * 0.00000060)
                        credits_to_deduct = calculate_klyro_credits_from_ai_cost(actual_cost, 4.00, 15.0)

                        supabase.rpc("process_ai_deduction", {
                            "p_user_id": user_id,
                            "p_credits_deducted": credits_to_deduct,
                            "p_feature": "HITL Semantic Healing",
                            "p_model": "gpt-4o-mini",
                            "p_input_tokens": input_tokens,
                            "p_output_tokens": output_tokens,
                            "p_actual_cost": actual_cost
                        }).execute()
                        print(f"💸 Successfully deducted {credits_to_deduct} Klyro Credits.")
                        
                except Exception as e:
                    print(f"❌ AI Engine failed: {str(e)}")
                    
        time.sleep(60)

if __name__ == "__main__":
    run_autonomous_agent()