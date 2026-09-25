import os
import requests
from dotenv import load_dotenv

load_dotenv()

class SAPIntegrationConnector:
    """
    Multi-tenant SAP BTP Integration Suite Connector.
    """
    def __init__(
        self,
        api_base_url: str = None,
        api_client_id: str = None,
        api_client_secret: str = None,
        token_url: str = None,
        runtime_url: str = None,
        runtime_client_id: str = None,
        runtime_client_secret: str = None
    ):
        self.api_base_url = api_base_url or os.getenv("SAP_API_BASE_URL", "")
        self.api_client_id = api_client_id or os.getenv("SAP_API_CLIENT_ID", "")
        self.api_client_secret = api_client_secret or os.getenv("SAP_API_CLIENT_SECRET", "")
        self.token_url = token_url or os.getenv("SAP_TOKEN_URL", "")
        self.base_runtime_url = runtime_url or os.getenv("SAP_RUNTIME_URL", "")
        self.runtime_client_id = runtime_client_id or os.getenv("SAP_RUNTIME_CLIENT_ID", "")
        self.runtime_client_secret = runtime_client_secret or os.getenv("SAP_RUNTIME_CLIENT_SECRET", "")
        self.mpl_api_url = f"{self.api_base_url}/api/v1/MessageProcessingLogs"

    def get_access_token(self, client_id: str = None, client_secret: str = None) -> str:
        cid = client_id or self.api_client_id
        csec = client_secret or self.api_client_secret
        payload = {"grant_type": "client_credentials"}
        
        response = requests.post(self.token_url, data=payload, auth=(cid, csec), timeout=15)
        response.raise_for_status()
        return response.json().get("access_token")

    def test_connection(self) -> dict:
        token = self.get_access_token()
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        response = requests.get(f"{self.mpl_api_url}?$top=1", headers=headers, timeout=15)
        response.raise_for_status()
        return {"connected": True, "status_code": response.status_code}

    def fetch_failed_logs(self) -> list:
        try:
            token = self.get_access_token()
            headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
            params = {"$filter": "Status eq 'FAILED'"}
            response = requests.get(self.mpl_api_url, headers=headers, params=params, timeout=20)
            response.raise_for_status()
            
            results = response.json().get("d", {}).get("results", [])
            return [
                {
                    "log_id": item.get("MessageGuid"),
                    "integration_flow_name": item.get("IntegrationFlowName"),
                    "error_message": item.get("AlternateWebLink") or "Processing failed in tenant.",
                    "status": item.get("Status")
                }
                for item in results
            ]
        except Exception as e:
            return []

    def fetch_payload_attachment(self, message_guid: str) -> str:
        try:
            token = self.get_access_token()
            headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
            url = f"{self.api_base_url}/api/v1/MessageProcessingLogs('{message_guid}')/Attachments"
            res = requests.get(url, headers=headers, timeout=15)
            res.raise_for_status()
            attachments = res.json().get("d", {}).get("results", [])
            if not attachments:
                return None
            
            attachment_id = attachments[0].get("Id")
            download_url = f"{self.api_base_url}/api/v1/MessageProcessingLogAttachments('{attachment_id}')/$value"
            payload_res = requests.get(download_url, headers=headers, timeout=15)
            payload_res.raise_for_status()
            return payload_res.text
        except Exception:
            return None

    def retrigger_message(self, runtime_endpoint_url: str, corrected_payload: str):
        try:
            token = self.get_access_token(self.runtime_client_id, self.runtime_client_secret)
            headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/xml"}
            response = requests.post(runtime_endpoint_url, headers=headers, data=corrected_payload, timeout=20)
            return {
                "status": "success" if response.status_code in [200, 201, 202] else "failed",
                "message": f"Retrigger returned status: {response.status_code}",
                "http_code": response.status_code
            }
        except Exception as e:
            return {"status": "error", "message": str(e), "http_code": 500}

sap_client = SAPIntegrationConnector()