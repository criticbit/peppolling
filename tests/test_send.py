import os
from datetime import date
from getpass import getpass

from peppolling import PeppolBookkeeping
from peppolling.peppol_bookkeeping import User

def get_env_or_prompt(env_name, prompt_text):
    value = os.getenv(env_name)
    if value:
        return value
    return getpass(prompt_text + ": ")

def main():
    api_key = get_env_or_prompt("PEPPYRUS_API_KEY", "Enter your Peppyrus API key")
    sender_peppol_id = get_env_or_prompt("PEPPOL_SENDER_ID", "Enter your sender Peppol ID")
    buyer_peppol_id = get_env_or_prompt("PEPPOL_BUYER_ID", "Enter a test buyer Peppol ID")

    bk = PeppolBookkeeping(
        peppol_api_key=api_key,
        peppol_endpoint="https://api.test.peppyrus.be/",
        sender_peppol_id=sender_peppol_id,
        sender_company="Test Supplier",
        sender_vat="BE0123456789",
        sender_street="Teststraat 1",
        sender_city="Brussel",
        sender_postal="1000",
        sender_country_code="BE"
    )

    # Ensure supplier exists
    supplier = bk.session.query(User).filter_by(company="Test Supplier").first()
    if not supplier:
        supplier = User(
            company="Test Supplier",
            vat_number="BE0123456789",
            peppol_id=sender_peppol_id
        )
        bk.session.add(supplier)
        bk.session.commit()

    # Ensure buyer exists
    buyer = bk.session.query(User).filter_by(company="Test Buyer").first()
    if not buyer:
        buyer = User(
            company="Test Buyer",
            vat_number="BE0999999999",
            peppol_id=buyer_peppol_id
        )
        bk.session.add(buyer)
        bk.session.commit()

    items = [
        {
            "name": "Test product",
            "description": "Peppolling test item",
            "quantity": 1,
            "unit_price": 10,
            "vat_pct": 0.21
        }
    ]

    xml_bytes = bk.generate_invoice_xml(
        supplier=supplier,
        buyer=buyer,
        items=items,
        invoice_id="TEST-INV-001",
        issue_date=date.today()
    )

    status, response = bk.send_invoice(xml_bytes)

    print("Status:", status)
    print("Response:", response)

if __name__ == "__main__":
    main()
