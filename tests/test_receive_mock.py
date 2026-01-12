import json
from unittest.mock import patch, MagicMock

from peppolling import PeppolBookkeeping

def test_receive_invoices_mock():
    # Fake Peppyrus list response
    fake_list = [
        {"id": "123", "sender": "0088:111", "date": "2025-01-01T10:00:00Z"}
    ]

    # Fake Peppyrus message detail with base64 XML
    fake_detail = {
        "document": "PD94bWwgdmVyc2lvbj0iMS4wIj8+Ckludm9pY2U+PC9JbnZvaWNlPg=="  # "<Invoice></Invoice>" base64
    }

    # Mock requests.get so it returns our fake responses
    with patch("requests.get") as mock_get:
        # First call → message/list
        mock_list_resp = MagicMock()
        mock_list_resp.status_code = 200
        mock_list_resp.json.return_value = fake_list

        # Second call → message/{id}
        mock_detail_resp = MagicMock()
        mock_detail_resp.status_code = 200
        mock_detail_resp.json.return_value = fake_detail

        mock_get.side_effect = [mock_list_resp, mock_detail_resp]

        bk = PeppolBookkeeping(peppol_api_key="dummy")

        results = bk.receive_invoices()

        assert len(results) == 1
        assert results[0]["message_id"] == "123"
