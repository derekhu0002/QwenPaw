from __future__ import annotations

import requests

base_url = "http://127.0.0.1:8091"

event = {
    "sourceSystem": "cloud_siem",
    "eventId": "siem-demo-20260612-0001",
    "eventTypeId": "correlation_rule_match",
    "schemaVersion": "1.0",
    "severity": "MEDIUM",
    "summary": "Correlation rule matched suspicious cloud activity",
    "occurredAt": "2026-06-12T03:15:00Z",
    "payload": {
        "ruleId": "CLOUD-RULE-1842",
        "assetId": "prod-cloud-account-12",
        "actionTaken": "opened-investigation",
    },
}

response = requests.post(
    f"{base_url}/security-center/v1/events",
    json=event,
    timeout=10,
)
response.raise_for_status()
print(response.json())