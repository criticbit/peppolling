import base64
from pathlib import Path
from unittest.mock import patch, MagicMock

from peppolling import PeppolBookkeeping

FIXTURE = Path(__file__).parent / "fixtures" / "invoice_minimal.xml"

def test_receive_invoices_mock():
    xml_bytes = FIXTURE.read_bytes()
    b64 = base64.b64encode(xml_bytes).decode()

    fake_list = [
        {"id": "123", "sender": "0088:111", "date": "2025-01-01T10:00:00Z"}
    ]

    fake_detail = {"document": b64}

    with patch("requests.get") as mock_get:
        mock_list_resp = MagicMock()
        mock_list_resp.status_code = 200
        mock_list_resp.json.return_value = fake_list

        mock_detail_resp = MagicMock()
        mock_detail_resp.status_code = 200
        mock_detail_resp.json.return_value = fake_detail

        mock_get.side_effect = [mock_list_resp, mock_detail_resp]

        bk = PeppolBookkeeping(peppol_api_key="dummy")

        results = bk.receive_invoices()

        assert len(results) == 1
        assert results[0]["invoice_id"] == "TEST-INV-001"
