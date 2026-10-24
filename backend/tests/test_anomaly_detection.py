from app.pipeline import anomaly_detection


def _severities(anomalies, category):
    return [a["severity"] for a in anomalies if a["category"] == category]


def test_invoice_amount_mismatch_detected():
    extraction = {
        "line_items": [{"description": "Widget A", "amount": 250.0}],
        "total": 999.0,
        "tax": 36.0,
        "due_date": None,
    }
    anomalies = anomaly_detection.detect_invoice_anomalies(extraction)
    assert "critical" in _severities(anomalies, "amount_mismatch")


def test_invoice_correct_math_no_mismatch():
    extraction = {
        "line_items": [{"description": "Widget A", "amount": 250.0}, {"description": "Widget B", "amount": 200.0}],
        "total": 486.0,
        "tax": 36.0,
        "due_date": None,
    }
    anomalies = anomaly_detection.detect_invoice_anomalies(extraction)
    assert _severities(anomalies, "amount_mismatch") == []


def test_duplicate_line_item_detected():
    extraction = {
        "line_items": [
            {"description": "Widget A", "amount": 250.0},
            {"description": "Widget A", "amount": 250.0},
        ],
        "total": 500.0,
        "tax": 0,
        "due_date": None,
    }
    anomalies = anomaly_detection.detect_invoice_anomalies(extraction)
    assert "warning" in _severities(anomalies, "duplicate_line_item")


def test_past_due_date_detected():
    extraction = {"line_items": [], "total": None, "tax": 0, "due_date": "March 15, 2024"}
    anomalies = anomaly_detection.detect_invoice_anomalies(extraction)
    assert "critical" in _severities(anomalies, "past_due_date")


def test_future_due_date_not_flagged():
    extraction = {"line_items": [], "total": None, "tax": 0, "due_date": "January 1, 2030"}
    anomalies = anomaly_detection.detect_invoice_anomalies(extraction)
    assert _severities(anomalies, "past_due_date") == []


def test_short_termination_notice_flagged():
    extraction = {"clauses": {"termination": {"notice_days": 5}}, "missing_standard_clauses": []}
    anomalies = anomaly_detection.detect_contract_anomalies(extraction)
    assert "warning" in _severities(anomalies, "termination_notice")


def test_reasonable_termination_notice_not_flagged():
    extraction = {"clauses": {"termination": {"notice_days": 30}}, "missing_standard_clauses": []}
    anomalies = anomaly_detection.detect_contract_anomalies(extraction)
    assert _severities(anomalies, "termination_notice") == []


def test_long_payment_terms_flagged():
    extraction = {"clauses": {"payment_terms": {"days": 120}}, "missing_standard_clauses": []}
    anomalies = anomaly_detection.detect_contract_anomalies(extraction)
    assert "warning" in _severities(anomalies, "payment_terms")


def test_asymmetric_liability_cap_flagged():
    extraction = {
        "clauses": {"liability_cap": {"amounts": ["$50,000", "$500,000"]}},
        "missing_standard_clauses": [],
    }
    anomalies = anomaly_detection.detect_contract_anomalies(extraction)
    assert "critical" in _severities(anomalies, "liability_asymmetry")


def test_missing_standard_clauses_reported_as_informational():
    extraction = {"clauses": {}, "missing_standard_clauses": ["payment_terms", "termination"]}
    anomalies = anomaly_detection.detect_contract_anomalies(extraction)
    assert all(a["severity"] == "informational" for a in anomalies if a["category"] == "missing_clause")
    assert len([a for a in anomalies if a["category"] == "missing_clause"]) == 2


def test_liabilities_exceeding_assets_flagged():
    extraction = {"metrics": {"total_assets": 1_800_000, "total_liabilities": 2_100_000}}
    anomalies = anomaly_detection.detect_financial_statement_anomalies(extraction)
    assert "critical" in _severities(anomalies, "liabilities_exceed_assets")


def test_healthy_balance_sheet_not_flagged():
    extraction = {"metrics": {"total_assets": 2_000_000, "total_liabilities": 800_000}}
    anomalies = anomaly_detection.detect_financial_statement_anomalies(extraction)
    assert _severities(anomalies, "liabilities_exceed_assets") == []


def test_yoy_change_exceeding_threshold_flagged():
    extraction = {"metrics": {"revenue": 2_000_000}}
    prior = {"revenue": 1_000_000}  # 100% change, exceeds default 35% threshold
    anomalies = anomaly_detection.detect_financial_statement_anomalies(extraction, prior_period_metrics=prior)
    assert "warning" in _severities(anomalies, "yoy_change")


def test_yoy_change_uses_comparative_column_from_statement():
    from app.pipeline import extraction
    text = "Income Statement\nTotal Revenue | 1,250,000 | 820,000\nNet Income | 95,000 | 88,000\n"
    stage2 = extraction.extract_financial_statement(text, [])
    assert stage2["prior_period_metrics"] == {"revenue": 820000.0, "net_income": 88000.0}
    anomalies = anomaly_detection.run_stage3("financial_statement", stage2)
    yoy = [a for a in anomalies if a["category"] == "yoy_change"]
    assert [a["evidence"]["metric"] for a in yoy] == ["revenue"]  # +52%; net income +8% stays quiet


def test_yoy_change_falls_back_to_prior_statement_in_project():
    stage2 = {"metrics": {"revenue": 500000.0}, "prior_period_metrics": {}}
    anomalies = anomaly_detection.run_stage3("financial_statement", stage2, {"revenue": 1000000.0})
    assert any(a["category"] == "yoy_change" for a in anomalies)
