import os
import base64
from datetime import datetime, date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from collections import defaultdict

import requests
from lxml import etree
from sqlalchemy import (
    create_engine, Column, Integer, String, Float, Boolean,
    DateTime, ForeignKey
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

# -------------------------
# SQLAlchemy setup
# -------------------------

Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    company = Column(String, nullable=False)
    name = Column(String)
    vat_number = Column(String)
    country_code = Column(String, default="BE")
    street = Column(String)
    city = Column(String)
    postal_code = Column(String)
    peppol_id = Column(String)  # e.g. "0088:123456789"


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    from_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    to_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    value = Column(Float, nullable=False)
    vat = Column(Float, default=0.0)
    vat_recovery = Column(Float, default=1.0)
    currency = Column(String, default="euro")
    start = Column(DateTime, nullable=False)
    end = Column(DateTime)
    intervat = Column(Boolean, default=False)
    annotation = Column(String)
    proof = Column(String)

    from_user = relationship("User", foreign_keys=[from_user_id])
    to_user = relationship("User", foreign_keys=[to_user_id])


class Invoice(Base):
    __tablename__ = "invoices"

    id = Column(Integer, primary_key=True)
    external_id = Column(String)  # UBL cbc:ID
    peppol_message_id = Column(String)
    supplier_id = Column(Integer, ForeignKey("users.id"))
    buyer_id = Column(Integer, ForeignKey("users.id"))
    issue_date = Column(DateTime)
    currency = Column(String)
    total_amount = Column(Float)
    vat_amount = Column(Float)
    transaction_id = Column(Integer, ForeignKey("transactions.id"))

    supplier = relationship("User", foreign_keys=[supplier_id])
    buyer = relationship("User", foreign_keys=[buyer_id])
    transaction = relationship("Transaction", foreign_keys=[transaction_id])


# -------------------------
# Peppol bookkeeping core
# -------------------------

class PeppolBookkeeping:
    """
    Minimal Peppol-based bookkeeping core for small companies.

    Features:
    - Generate EN16931/Peppol BIS Billing 3.0 UBL invoices
    - Send invoices via Peppyrus
    - Receive invoices from Peppyrus
    - Import invoices into a simple bookkeeping model
    """

    def __init__(
        self,
        db_url="sqlite:///bookkeeping.db",
        peppol_api_key=None,
        peppol_endpoint="https://api.test.peppyrus.be/",
        sender_peppol_id=None,
        sender_company=None,
        sender_vat=None,
        sender_street=None,
        sender_city=None,
        sender_postal=None,
        sender_country_code="BE"
    ):
        # DB setup
        self.engine = create_engine(db_url)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.session = self.Session()

        # Peppol / Peppyrus config
        self.PEPPOL_API_KEY = peppol_api_key or os.getenv("PEPPOL_API_KEY", "")
        self.PEPPOL_ENDPOINT = peppol_endpoint.rstrip("/") + "/"
        self.SENDER_PEPPOL_ID = sender_peppol_id or os.getenv("PEPPOL_SENDER_ID", "")

        # Sender (supplier) info
        self.sender_company = sender_company or "Example Supplier"
        self.sender_vat = (sender_vat or "BE0123456789").replace(" ", "").replace(".", "")
        self.sender_street = sender_street or "Example Street 1"
        self.sender_city = sender_city or "Example City"
        self.sender_postal = sender_postal or "1000"
        self.sender_country_code = sender_country_code

    # -------------------------
    # Helpers
    # -------------------------

    @staticmethod
    def _qname(ns, tag):
        return etree.QName(ns, tag)

    @staticmethod
    def _safe_str(val):
        return "" if val is None else str(val)

    @staticmethod
    def _d2(value) -> Decimal:
        return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    @staticmethod
    def _d0(value) -> Decimal:
        return Decimal(str(value))

    @staticmethod
    def _fmt_amount(value: Decimal) -> str:
        return str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

    # -------------------------
    # Transaction creation
    # -------------------------

    def create_transaction_record(
        self,
        name,
        from_user_id,
        to_user_id,
        value,
        vat,
        vat_recovery,
        currency,
        start,
        end=None,
        intervat=False,
        annotation=None,
        proof_filename=None
    ):
        record = Transaction()
        record.name = name
        record.from_user_id = from_user_id
        record.to_user_id = to_user_id
        record.value = value
        record.vat = vat
        record.vat_recovery = vat_recovery
        record.currency = currency
        record.start = start
        record.end = end
        record.intervat = intervat
        record.annotation = annotation
        record.proof = proof_filename

        self.session.add(record)
        self.session.commit()
        return record

    # -------------------------
    # UBL invoice generation
    # -------------------------

    def generate_invoice_xml(self, supplier: User, buyer: User, items, invoice_id: str, issue_date: date, due_date: date = None):
        """
        Generate a UBL 2.1 EN16931/Peppol BIS Billing 3.0 invoice.

        items: list of dicts with keys:
            - name
            - description
            - quantity
            - unit_price
            - vat_pct (e.g. 0.21)
        """

        ns_ubl = "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
        ns_cbc = "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"
        ns_cac = "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"

        qname = self._qname
        d0 = self._d0
        d2 = self._d2
        fmt_amount = self._fmt_amount
        safe_str = self._safe_str

        if not due_date:
            due_date = issue_date + timedelta(days=30)

        invoice_et = etree.Element("Invoice", nsmap={None: ns_ubl, "cbc": ns_cbc, "cac": ns_cac})

        # HEADER
        etree.SubElement(invoice_et, qname(ns_cbc, "CustomizationID")).text = (
            "urn:cen.eu:en16931:2017#compliant#urn:fdc:peppol.eu:2017:poacc:billing:3.0"
        )
        etree.SubElement(invoice_et, qname(ns_cbc, "ProfileID")).text = (
            "urn:fdc:peppol.eu:2017:poacc:billing:01:1.0"
        )
        etree.SubElement(invoice_et, qname(ns_cbc, "ID")).text = invoice_id
        etree.SubElement(invoice_et, qname(ns_cbc, "IssueDate")).text = str(issue_date)
        etree.SubElement(invoice_et, qname(ns_cbc, "InvoiceTypeCode")).text = "380"
        etree.SubElement(invoice_et, qname(ns_cbc, "DocumentCurrencyCode")).text = "EUR"
        etree.SubElement(invoice_et, qname(ns_cbc, "LineCountNumeric")).text = str(len(items))
        etree.SubElement(invoice_et, qname(ns_cbc, "BuyerReference")).text = buyer.company

        # SELLER
        supplier_party = etree.SubElement(invoice_et, qname(ns_cac, "AccountingSupplierParty"))
        party = etree.SubElement(supplier_party, qname(ns_cac, "Party"))

        if supplier.peppol_id:
            scheme = supplier.peppol_id.split(":")[0]
            etree.SubElement(party, qname(ns_cbc, "EndpointID"), schemeID=scheme).text = supplier.peppol_id

        party_ident = etree.SubElement(party, qname(ns_cac, "PartyIdentification"))
        etree.SubElement(party_ident, qname(ns_cbc, "ID"), schemeID="0208").text = supplier.vat_number or "0000000000"

        party_name = etree.SubElement(party, qname(ns_cac, "PartyName"))
        etree.SubElement(party_name, qname(ns_cbc, "Name")).text = supplier.company

        address = etree.SubElement(party, qname(ns_cac, "PostalAddress"))
        etree.SubElement(address, qname(ns_cbc, "StreetName")).text = supplier.street or ""
        etree.SubElement(address, qname(ns_cbc, "CityName")).text = supplier.city or ""
        etree.SubElement(address, qname(ns_cbc, "PostalZone")).text = supplier.postal_code or ""
        country = etree.SubElement(address, qname(ns_cac, "Country"))
        etree.SubElement(country, qname(ns_cbc, "IdentificationCode")).text = supplier.country_code or "BE"

        party_tax = etree.SubElement(party, qname(ns_cac, "PartyTaxScheme"))
        etree.SubElement(party_tax, qname(ns_cbc, "CompanyID")).text = supplier.vat_number or ""
        tax_scheme = etree.SubElement(party_tax, qname(ns_cac, "TaxScheme"))
        etree.SubElement(tax_scheme, qname(ns_cbc, "ID")).text = "VAT"

        party_legal = etree.SubElement(party, qname(ns_cac, "PartyLegalEntity"))
        etree.SubElement(party_legal, qname(ns_cbc, "RegistrationName")).text = supplier.company

        # BUYER
        customer_party = etree.SubElement(invoice_et, qname(ns_cac, "AccountingCustomerParty"))
        party_c = etree.SubElement(customer_party, qname(ns_cac, "Party"))

        if buyer.peppol_id:
            buyer_scheme = buyer.peppol_id.split(":")[0]
            etree.SubElement(party_c, qname(ns_cbc, "EndpointID"), schemeID=buyer_scheme).text = buyer.peppol_id

        party_c_name = etree.SubElement(party_c, qname(ns_cac, "PartyName"))
        etree.SubElement(party_c_name, qname(ns_cbc, "Name")).text = buyer.company

        address_c = etree.SubElement(party_c, qname(ns_cac, "PostalAddress"))
        etree.SubElement(address_c, qname(ns_cbc, "StreetName")).text = buyer.street or ""
        etree.SubElement(address_c, qname(ns_cbc, "CityName")).text = buyer.city or ""
        etree.SubElement(address_c, qname(ns_cbc, "PostalZone")).text = buyer.postal_code or ""
        country_c = etree.SubElement(address_c, qname(ns_cac, "Country"))
        etree.SubElement(country_c, qname(ns_cbc, "IdentificationCode")).text = buyer.country_code or "BE"

        party_c_legal = etree.SubElement(party_c, qname(ns_cac, "PartyLegalEntity"))
        etree.SubElement(party_c_legal, qname(ns_cbc, "RegistrationName")).text = buyer.company

        # COMPUTE TOTALS
        vat_groups = defaultdict(lambda: {"taxable": Decimal("0.00"), "tax": Decimal("0.00")})
        total_without_tax = Decimal("0.00")
        total_tax = Decimal("0.00")

        for item in items:
            quantity = d0(item.get("quantity", 0))
            unit_price = d2(item.get("unit_price", 0))
            line_total = d2(quantity * unit_price)

            vat_pct = Decimal(str(item.get("vat_pct", 0)))
            if vat_pct < Decimal("0"):
                vat_pct = Decimal("0")

            vat_amount = line_total * vat_pct
            vat_groups[vat_pct]["taxable"] += line_total
            vat_groups[vat_pct]["tax"] += vat_amount

            total_without_tax += line_total
            total_tax += vat_amount

        # TAX TOTAL
        tax_total = etree.SubElement(invoice_et, qname(ns_cac, "TaxTotal"))
        etree.SubElement(tax_total, qname(ns_cbc, "TaxAmount"), currencyID="EUR").text = fmt_amount(total_tax)

        for vat_pct, values in vat_groups.items():
            subtotal = etree.SubElement(tax_total, qname(ns_cac, "TaxSubtotal"))
            etree.SubElement(subtotal, qname(ns_cbc, "TaxableAmount"), currencyID="EUR").text = fmt_amount(values["taxable"])
            etree.SubElement(subtotal, qname(ns_cbc, "TaxAmount"), currencyID="EUR").text = fmt_amount(values["tax"])

            category = etree.SubElement(subtotal, qname(ns_cac, "TaxCategory"))
            etree.SubElement(category, qname(ns_cbc, "ID")).text = "S"
            etree.SubElement(category, qname(ns_cbc, "Percent")).text = fmt_amount(vat_pct * Decimal("100"))
            scheme = etree.SubElement(category, qname(ns_cac, "TaxScheme"))
            etree.SubElement(scheme, qname(ns_cbc, "ID")).text = "VAT"

        # PAYMENT TERMS (BT-9 via Note)
        payment_terms = etree.SubElement(invoice_et, qname(ns_cac, "PaymentTerms"))
        etree.SubElement(payment_terms, qname(ns_cbc, "Note")).text = f"Payment due by {due_date}"

        # LEGAL MONETARY TOTAL
        monetary = etree.SubElement(invoice_et, qname(ns_cac, "LegalMonetaryTotal"))
        etree.SubElement(monetary, qname(ns_cbc, "LineExtensionAmount"), currencyID="EUR").text = fmt_amount(total_without_tax)
        etree.SubElement(monetary, qname(ns_cbc, "TaxExclusiveAmount"), currencyID="EUR").text = fmt_amount(total_without_tax)
        etree.SubElement(monetary, qname(ns_cbc, "TaxInclusiveAmount"), currencyID="EUR").text = fmt_amount(total_without_tax + total_tax)
        etree.SubElement(monetary, qname(ns_cbc, "PayableAmount"), currencyID="EUR").text = fmt_amount(total_without_tax + total_tax)

        # INVOICE LINES
        for idx, item in enumerate(items, start=1):
            quantity = d0(item.get("quantity", 0))
            unit_price = d2(item.get("unit_price", 0))
            line_total = d2(quantity * unit_price)

            line = etree.SubElement(invoice_et, qname(ns_cac, "InvoiceLine"))
            etree.SubElement(line, qname(ns_cbc, "ID")).text = str(idx)
            etree.SubElement(line, qname(ns_cbc, "InvoicedQuantity"), unitCode="EA").text = str(quantity)
            etree.SubElement(line, qname(ns_cbc, "LineExtensionAmount"), currencyID="EUR").text = fmt_amount(line_total)

            item_elem = etree.SubElement(line, qname(ns_cac, "Item"))
            desc = safe_str(item.get("description", ""))
            if desc:
                etree.SubElement(item_elem, qname(ns_cbc, "Description")).text = desc

            item_name = safe_str(item.get("name", "")) or desc or f"Item {idx}"
            etree.SubElement(item_elem, qname(ns_cbc, "Name")).text = item_name

            vat_pct = Decimal(str(item.get("vat_pct", 0)))
            if vat_pct < Decimal("0"):
                vat_pct = Decimal("0")

            tax_cat = etree.SubElement(item_elem, qname(ns_cac, "ClassifiedTaxCategory"))
            etree.SubElement(tax_cat, qname(ns_cbc, "ID")).text = "S"
            etree.SubElement(tax_cat, qname(ns_cbc, "Percent")).text = fmt_amount(vat_pct * Decimal("100"))
            tax_scheme = etree.SubElement(tax_cat, qname(ns_cac, "TaxScheme"))
            etree.SubElement(tax_scheme, qname(ns_cbc, "ID")).text = "VAT"

            price = etree.SubElement(line, qname(ns_cac, "Price"))
            etree.SubElement(price, qname(ns_cbc, "PriceAmount"), currencyID="EUR").text = fmt_amount(unit_price)

        # PAYMENT MEANS (optional, after lines)
        payment_means = etree.SubElement(invoice_et, qname(ns_cac, "PaymentMeans"))
        etree.SubElement(payment_means, qname(ns_cbc, "PaymentMeansCode")).text = "31"
        etree.SubElement(payment_means, qname(ns_cbc, "PaymentDueDate")).text = str(due_date)

        xml_bytes = etree.tostring(invoice_et, pretty_print=True, xml_declaration=True, encoding="UTF-8")
        return xml_bytes

    # -------------------------
    # Sending via Peppyrus
    # -------------------------

    def send_invoice(self, xml_bytes: bytes):
        headers = {
            "accept": "application/json",
            "X-Api-Key": self.PEPPOL_API_KEY,
            "Content-Type": "application/xml"
        }
        resp = requests.post(
            self.PEPPOL_ENDPOINT + "v1/message/send",
            headers=headers,
            data=xml_bytes
        )
        return resp.status_code, resp.text

    # -------------------------
    # Receiving via Peppyrus
    # -------------------------

    def receive_invoices(self):
        headers = {
            "accept": "application/json",
            "X-Api-Key": self.PEPPOL_API_KEY
        }

        resp = requests.get(
            self.PEPPOL_ENDPOINT + "v1/message/list",
            headers=headers,
            params={"folder": "INBOX"}
        )

        if resp.status_code == 404:
            return []

        if resp.status_code != 200:
            raise RuntimeError(f"Error retrieving invoices: {resp.status_code}, {resp.text}")

        messages = resp.json() or []
        results = []

        for msg in messages:
            msg_id = msg["id"]
            detail_resp = requests.get(
                self.PEPPOL_ENDPOINT + f"v1/message/{msg_id}",
                headers=headers
            )
            if detail_resp.status_code != 200:
                continue

            detail = detail_resp.json()
            result = self.process_incoming_invoice(msg, detail)
            results.append(result)

        return results

    # -------------------------
    # Process one incoming invoice
    # -------------------------

    def process_incoming_invoice(self, msg_meta, msg_detail):
        b64_xml = msg_detail.get("document")
        if not b64_xml:
            return {"id": msg_meta["id"], "error": "No document found"}

        xml_bytes = base64.b64decode(b64_xml)
        root = etree.fromstring(xml_bytes)

        ns = {
            "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
            "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
        }

        invoice_id = root.findtext("cbc:ID", namespaces=ns)
        issue_date = root.findtext("cbc:IssueDate", namespaces=ns)
        currency = root.findtext("cbc:DocumentCurrencyCode", namespaces=ns)

        supplier_name = root.findtext("cac:AccountingSupplierParty/cac:Party/cac:PartyName/cbc:Name", namespaces=ns)
        buyer_name = root.findtext("cac:AccountingCustomerParty/cac:Party/cac:PartyName/cbc:Name", namespaces=ns)

        total_amount = root.findtext("cac:LegalMonetaryTotal/cbc:PayableAmount", namespaces=ns)
        total_amount = float(total_amount) if total_amount else 0.0

        vat_total = 0.0
        for ts in root.findall("cac:TaxTotal/cac:TaxSubtotal", namespaces=ns):
            vat_amount = ts.findtext("cbc:TaxAmount", namespaces=ns)
            if vat_amount:
                vat_total += float(vat_amount)

        # Ensure supplier and buyer exist as Users
        supplier = self.session.query(User).filter_by(company=supplier_name).first()
        if not supplier:
            supplier = User(company=supplier_name)
            self.session.add(supplier)
            self.session.commit()

        buyer = self.session.query(User).filter_by(company=buyer_name).first()
        if not buyer:
            buyer = User(company=buyer_name)
            self.session.add(buyer)
            self.session.commit()

        # Create transaction
        start_dt = datetime.fromisoformat(issue_date) if issue_date else datetime.utcnow()
        record = self.create_transaction_record(
            name=f"Invoice {invoice_id}",
            from_user_id=supplier.id,
            to_user_id=buyer.id,
            value=total_amount - vat_total,
            vat=vat_total,
            vat_recovery=1.0,
            currency=currency or "EUR",
            start=start_dt,
            annotation=f"Imported from Peppol message {msg_meta['id']}"
        )

        # Store invoice record
        inv = Invoice()
        inv.external_id = invoice_id
        inv.peppol_message_id = msg_meta["id"]
        inv.supplier_id = supplier.id
        inv.buyer_id = buyer.id
        inv.issue_date = start_dt
        inv.currency = currency or "EUR"
        inv.total_amount = total_amount
        inv.vat_amount = vat_total
        inv.transaction_id = record.id

        self.session.add(inv)
        self.session.commit()

        return {
            "message_id": msg_meta["id"],
            "invoice_id": invoice_id,
            "supplier": supplier_name,
            "buyer": buyer_name,
            "date": issue_date,
            "total": total_amount,
            "vat": vat_total,
            "transaction_id": record.id,
            "invoice_db_id": inv.id
        }


# -------------------------
# Example usage (CLI)
# -------------------------

if __name__ == "__main__":
    bk = PeppolBookkeeping()

    # Example: list received invoices and import them
    try:
        results = bk.receive_invoices()
        for r in results:
            print("Imported:", r)
    except Exception as e:
        print("Error:", e)
