import os
import time
from supabase import create_client
from llm_service import analyze_and_correct_payload

supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_KEY")
supabase = create_client(supabase_url, supabase_key) if supabase_url and supabase_key else None

retry_cache = {}
MAX_RETRIES = 3

def run_autonomous_agent():
    # Import active_tenants locally to prevent circular import errors
    from main import active_tenants
    print("🤖 Starting 24/7 Multi-Tenant SAP CPI Agent...")
    
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
                    raw_fixed_payload = analyze_and_correct_payload(
                        integration_flow_name=failed_iflow,
                        error_message=error_msg,
                        raw_payload=broken_payload
                    )
                    fixed_payload = raw_fixed_payload.replace("```xml", "").replace("```json", "").replace("```", "").strip()
                    
                    if supabase:
                        try:
                            rule_response = supabase.table("routing_rules").select("endpoint_path") \
                                .eq("tenant_id", tenant_id).eq("iflow_name", failed_iflow).execute()

                            if rule_response.data:
                                endpoint_path = rule_response.data[0]['endpoint_path']
                                runtime_url = f"{sap_client.base_runtime_url}/http{endpoint_path}"
                                
                                result = sap_client.retrigger_message(runtime_url, fixed_payload)
                                print(f"📡 Dynamic Auto-Retrigger Status for {failed_iflow}: {result.get('message')}")
                                
                                if result.get("http_code") in [200, 201, 202]:
                                     retry_cache.pop(log_id, None)
                            else:
                                print(f"⚠️ No routing rule defined in Supabase for '{failed_iflow}'. Parking in HITL queue.")
                        except Exception as e:
                             print(f"❌ Supabase query failed: {str(e)}")
                    else:
                        print("⚠️ Supabase credentials missing. Cannot fetch routing rules. Parking in HITL queue.")
                        
                except Exception as e:
                    print(f"❌ AI Engine failed: {str(e)}")
                    
        time.sleep(60)

if __name__ == "__main__":
    run_autonomous_agent()