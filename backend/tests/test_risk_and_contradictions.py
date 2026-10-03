from app.pipeline import risk_scoring, contradiction_detection, anomaly_detection


def test_no_anomalies_gives_zero_risk():
    result = risk_scoring.run_stage4([])
    assert result["risk_score"] == 0.0


def test_critical_anomaly_scores_higher_than_many_informational():
    critical = [{"severity": "critical", "category": "amount_mismatch"}]
    many_informational = [{"severity": "informational", "category": "missing_clause"}] * 3
    critical_score = risk_scoring.run_stage4(critical)["risk_score"]
    informational_score = risk_scoring.run_stage4(many_informational)["risk_score"]
    assert critical_score > informational_score


def test_risk_score_capped_at_100():
    many_criticals = [{"severity": "critical", "category": "amount_mismatch"}] * 20
    result = risk_scoring.run_stage4(many_criticals)
    assert result["risk_score"] <= 100


def test_breakdown_groups_by_category():
    anomalies = [
        {"severity": "critical", "category": "amount_mismatch"},       # financial
        {"severity": "warning", "category": "termination_notice"},     # contractual
        {"severity": "warning", "category": "duplicate_line_item"},    # data_quality
    ]
    result = risk_scoring.run_stage4(anomalies)
    assert result["breakdown"]["financial"] > 0
    assert result["breakdown"]["contractual"] > 0
    assert result["breakdown"]["data_quality"] > 0


def test_contradiction_between_revenue_and_invoice_sum():
    docs = [
        {"id": "stmt-1", "document_type": "financial_statement",
         "extracted_entities": {"metrics": {"revenue": 2_400_000}}, "primary_parties": []},
        {"id": "inv-1", "document_type": "invoice",
         "extracted_entities": {"total": 999.0}, "primary_parties": []},
    ]
    contradictions = contradiction_detection.find_contradictions(docs)
    assert len(contradictions) == 1
    assert contradictions[0]["field"] == "revenue_vs_invoice_total"


def test_no_contradiction_when_values_are_close():
    docs = [
        {"id": "stmt-1", "document_type": "financial_statement",
         "extracted_entities": {"metrics": {"revenue": 1000.0}}, "primary_parties": []},
        {"id": "inv-1", "document_type": "invoice",
         "extracted_entities": {"total": 950.0}, "primary_parties": []},
    ]
    contradictions = contradiction_detection.find_contradictions(docs)
    assert contradictions == []


def test_mismatched_payment_terms_between_shared_party_contracts():
    docs = [
        {"id": "c1", "document_type": "contract",
         "extracted_entities": {"clauses": {"payment_terms": {"days": 30}}},
         "primary_parties": ["Acme Manufacturing Inc."]},
        {"id": "c2", "document_type": "contract",
         "extracted_entities": {"clauses": {"payment_terms": {"days": 60}}},
         "primary_parties": ["Acme Manufacturing Inc."]},
    ]
    contradictions = contradiction_detection.find_contradictions(docs)
    assert any(c["field"] == "payment_terms_days" for c in contradictions)


def test_no_payment_terms_contradiction_without_shared_party():
    docs = [
        {"id": "c1", "document_type": "contract",
         "extracted_entities": {"clauses": {"payment_terms": {"days": 30}}},
         "primary_parties": ["Company A"]},
        {"id": "c2", "document_type": "contract",
         "extracted_entities": {"clauses": {"payment_terms": {"days": 60}}},
         "primary_parties": ["Company B"]},
    ]
    contradictions = contradiction_detection.find_contradictions(docs)
    assert contradictions == []


def test_single_document_produces_no_contradictions():
    docs = [{"id": "c1", "document_type": "contract", "extracted_entities": {}, "primary_parties": []}]
    assert contradiction_detection.find_contradictions(docs) == []


def test_invoice_vendor_matches_contract_party_for_payment_term_contradiction():
    docs = [
        {"id": "c1", "document_type": "contract",
         "extracted_entities": {"clauses": {"payment_terms": {"days": 30}}},
         "primary_parties": ["Acme Manufacturing Inc."]},
        {"id": "i1", "document_type": "invoice",
         "extracted_entities": {"payment_terms_days": 60, "vendor": "Acme Manufacturing"},
         "primary_parties": []},
    ]
    contradictions = contradiction_detection.find_contradictions(docs)
    assert any(c["field"] == "payment_terms_days" for c in contradictions)


def test_financial_ratio_outside_configured_range_is_flagged():
    extraction = {"metrics": {"revenue": 1000, "net_income": 100, "total_assets": 1000, "total_liabilities": 900}}
    anomalies = anomaly_detection.detect_financial_statement_anomalies(extraction)
    assert any(a["category"] == "industry_ratio_out_of_range" for a in anomalies)
