from unittest.mock import patch, MagicMock
from peppolling import PeppolBookkeeping

def test_send_invoice_mock():
    bk = PeppolBookkeeping(peppol_api_key="dummy")

    xml_bytes = b"<Invoice></Invoice>"

    with patch("requests.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = '{"messageId": "ABC123"}'
        mock_post.return_value = mock_resp

        status, response = bk.send_invoice(xml_bytes)

        assert status == 200
        assert "ABC123" in response
