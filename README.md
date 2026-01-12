### peppolling

A lightweight, open‑source Python toolkit that helps small Belgian companies work with **Peppol** for sending, receiving, and processing electronic invoices.  
It includes:

- A minimal bookkeeping model (Users, Transactions, Invoices)  
- A Peppol BIS Billing 3.0 compliant UBL invoice generator  
- Integration with the **Peppyrus** API for sending and receiving invoices  
- Automatic import of received invoices into your bookkeeping  
- A simple SQLAlchemy-based storage layer  

The goal is to make Peppol accessible for freelancers, small businesses, and developers who want a clean, understandable, and fully open solution without vendor lock-in.

---

## Features

### ✔ Generate UBL 2.1 EN16931 / Peppol BIS Billing 3.0 invoices  
Fully standards-compliant XML generation, including:

- Supplier & buyer party structures  
- VAT breakdowns  
- Invoice lines  
- Payment terms  
- Legal monetary totals  
- Correct element ordering for Peppol validation  

### ✔ Send invoices via Peppyrus  
A simple wrapper around the Peppyrus /message/send endpoint.

### ✔ Receive invoices from Peppyrus  
Fetch messages from the Peppol inbox, decode base64 XML, and parse UBL invoices.

### ✔ Automatic bookkeeping import  
Received invoices are converted into:

- A `Transaction` record  
- An `Invoice` record  
- Linked supplier and buyer `User` entries  

### ✔ SQLite by default  
Works out of the box with:

```
sqlite:///bookkeeping.db
```

But you can point it to any SQLAlchemy-compatible database.

---

## Installation

Once published to PyPI:

```
pip install peppolling
```

For now, if installing locally:

```
pip install .
```

---

## Quick Start

```python
from peppolling import PeppolBookkeeping

bk = PeppolBookkeeping(
    peppol_api_key="YOUR_PEPPRUS_API_KEY",
    sender_peppol_id="YOUR_PEPPOL_ID"
)

# Receive and import invoices
results = bk.receive_invoices()
for r in results:
    print("Imported:", r)
```

---

## Generating and sending an invoice

```python
supplier = bk.session.query(User).filter_by(company="My Company").first()
buyer = bk.session.query(User).filter_by(company="Customer NV").first()

items = [
    {
        "name": "Consulting",
        "description": "Software development services",
        "quantity": 10,
        "unit_price": 75,
        "vat_pct": 0.21
    }
]

xml_bytes = bk.generate_invoice_xml(
    supplier=supplier,
    buyer=buyer,
    items=items,
    invoice_id="INV-2025-001",
    issue_date=date.today()
)

status, response = bk.send_invoice(xml_bytes)
print(status, response)
```

---

## Receiving and importing invoices

```python
results = bk.receive_invoices()

for invoice in results:
    print(invoice["invoice_id"], invoice["total"])
```

This automatically:

- Decodes the UBL XML  
- Extracts supplier, buyer, totals, VAT  
- Creates a `Transaction`  
- Stores an `Invoice` record  

---

## Database Models

The package includes three simple SQLAlchemy models:

- `User`  
- `Transaction`  
- `Invoice`  

These can be extended or replaced depending on your needs.

---

## Configuration

You can configure:

- Database URL  
- Peppyrus API endpoint  
- Peppol sender ID  
- Sender company details  

Example:

```python
bk = PeppolBookkeeping(
    db_url="sqlite:///mybooks.db",
    peppol_api_key="xxx",
    peppol_endpoint="https://api.test.peppyrus.be/",
    sender_peppol_id="0088:123456789",
    sender_company="My Company",
    sender_vat="BE0123456789",
    sender_street="Main Street 1",
    sender_city="Brussels",
    sender_postal="1000",
    sender_country_code="BE"
)
```

---

## Why this project exists

Many small Belgian companies struggle with Peppol integration.  
This project aims to:

- Lower the barrier to entry  
- Provide a transparent, open-source alternative  
- Offer a simple bookkeeping workflow that can be extended or embedded  
- Help freelancers and small businesses stay compliant without expensive software  

---

## License

MIT License — free to use, modify, and distribute.

---

## Contributing

Pull requests, issues, and improvements are welcome.  
If you build something on top of this, consider sharing it back with the community.

---

## Roadmap

- CLI (peppolling send, peppolling receive)  
- Optional web dashboard  
- Support for credit notes  
- Support for attachments  
- SMP lookup helper  
- VAT reporting helpers  
