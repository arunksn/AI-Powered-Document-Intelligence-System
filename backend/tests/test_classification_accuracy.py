"""
Day 2 acceptance check: the Stage 1 classifier must reach at least 85%
accuracy on a 20-document test set spanning every document type. The
samples are short, realistic excerpts in the wording each type actually
uses, not keyword lists, so this measures the real scoring logic.
"""
from app.pipeline.classification import classify_document_type

LABELLED_SAMPLES = [
    # contract
    ("contract", "MASTER SERVICES AGREEMENT. This Agreement is made between Acme Inc. and Beta LLC. "
                 "The parties hereby agree as follows. Termination: either party may terminate on 60 days notice. "
                 "Governing law: Delaware."),
    ("contract", "SUPPLY AGREEMENT between Supplier and Buyer. Term of this Agreement is two years. "
                 "Each party shall perform its obligations. Termination for convenience requires 90 days notice."),
    ("contract", "Consulting Agreement. Consultant and Company hereby agree that Consultant will provide advisory "
                 "services. This agreement shall be governed by the laws of California. Either party may terminate."),
    ("contract", "LEASE AGREEMENT. Landlord and Tenant hereby agree to the lease of the premises. "
                 "The term of this agreement is 12 months. Governing law: New York."),
    # nda
    ("nda", "MUTUAL NON-DISCLOSURE AGREEMENT. The Receiving Party shall hold the Disclosing Party's "
            "Confidential Information in strict confidence for 3 years."),
    ("nda", "This NDA governs Confidential Information exchanged between the parties. The receiving party "
            "may not disclose confidential information to third parties."),
    ("nda", "Non-Disclosure Agreement. Disclosing Party will share technical data. Receiving Party agrees "
            "to use Confidential Information only to evaluate the proposed transaction."),
    # invoice
    ("invoice", "INVOICE. Invoice Number: INV-2201. Bill To: Northwind Traders. Item: Consulting hours. "
                "Amount Due: $4,500.00. Due Date: 2026-11-30."),
    ("invoice", "Tax Invoice #8812. Bill to: Globex Corp. Description Qty Price Amount. Subtotal 900. "
                "Total amount due 990. Remit payment to Acme Supplies."),
    ("invoice", "Invoice number 55-A. Services rendered in October. Please remit payment within 30 days. "
                "Amount due: $12,000."),
    ("invoice", "INVOICE - Bill To: Initech. Line items: hosting, support. Amount due upon receipt."),
    # financial_statement
    ("financial_statement", "Consolidated Balance Sheet as of December 31, 2025. Total assets 4,200,000. "
                            "Total liabilities 2,100,000. Shareholders equity 2,100,000."),
    ("financial_statement", "Income Statement for the fiscal year ended June 30, 2025. Revenue 8,000,000. "
                            "Operating expenses 6,500,000. Net income 1,100,000."),
    ("financial_statement", "Statement of Cash Flow for fiscal year 2024. Net cash flow from operations 300,000. "
                            "Net income 250,000."),
    ("financial_statement", "Annual financial statements: balance sheet, income statement and cash flow statement "
                            "for fiscal year 2025."),
    # rfp
    ("rfp", "REQUEST FOR PROPOSAL. Northwind invites vendors to respond. Scope of work: data migration. "
            "Proposal submission deadline: April 1."),
    ("rfp", "RFP 2026-07: Facilities maintenance. Scope of Work attached. Bid deadline is May 15. "
            "Late proposals will not be considered."),
    ("rfp", "This Request for Proposal seeks bids for IT support. Proposal submission must include pricing. "
            "Bid deadline: 5pm EST."),
    # other
    ("other", "Meeting notes from the quarterly offsite. Discussed hiring plans and the new office layout."),
    ("other", "Welcome to the employee handbook. Please read the sections on holidays and dress code."),
]


def test_classifier_accuracy_meets_85_percent_on_20_documents():
    assert len(LABELLED_SAMPLES) == 20
    assert {label for label, _ in LABELLED_SAMPLES} == {
        "contract", "nda", "invoice", "financial_statement", "rfp", "other",
    }
    misclassified = [
        (label, predicted, text[:50])
        for label, text in LABELLED_SAMPLES
        if (predicted := classify_document_type(text)) != label
    ]
    accuracy = 1 - len(misclassified) / len(LABELLED_SAMPLES)
    assert accuracy >= 0.85, f"accuracy {accuracy:.0%}, misclassified: {misclassified}"
