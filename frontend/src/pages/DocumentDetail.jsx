import { useEffect, useState, useCallback } from "react";
import { useParams, Link, useNavigate } from "react-router-dom";
import { api } from "../api";
import SeverityBadge from "../components/SeverityBadge.jsx";
import RiskChart from "../components/RiskChart.jsx";
import CrmSyncPanel from "../components/CrmSyncPanel.jsx";

function EntityField({ label, value }) {
  if (value === null || value === undefined || value === "" || (Array.isArray(value) && value.length === 0)) return null;
  return (
    <div className="border-b border-hairline/60 py-2 last:border-b-0">
      <div className="text-xs font-mono uppercase tracking-wide text-inkfaint">{label}</div>
      <div className="text-sm text-ink mt-0.5">
        {Array.isArray(value) ? value.join(", ") : String(value)}
      </div>
    </div>
  );
}

function ExtractionPanel({ documentType, entities }) {
  if (!entities) return null;

  if (documentType === "invoice") {
    return (
      <div>
        <div className="grid grid-cols-2 gap-x-6">
          <EntityField label="Vendor" value={entities.vendor} />
          <EntityField label="Invoice number" value={entities.invoice_number} />
          <EntityField label="Total" value={entities.total != null ? `$${entities.total.toLocaleString()}` : null} />
          <EntityField label="Tax" value={entities.tax != null ? `$${entities.tax.toLocaleString()}` : null} />
          <EntityField label="Due date" value={entities.due_date} />
        </div>
        {entities.line_items?.length > 0 && (
          <div className="mt-4">
            <div className="text-xs font-mono uppercase tracking-wide text-inkfaint mb-2">Line items</div>
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs font-mono text-inkfaint uppercase border-b border-hairline">
                  <th className="pb-1 font-normal">Description</th>
                  <th className="pb-1 font-normal text-right">Qty</th>
                  <th className="pb-1 font-normal text-right">Unit price</th>
                  <th className="pb-1 font-normal text-right">Amount</th>
                </tr>
              </thead>
              <tbody>
                {entities.line_items.map((li, i) => (
                  <tr key={i} className="border-b border-hairline/40 last:border-b-0">
                    <td className="py-1.5">{li.description || "—"}</td>
                    <td className="py-1.5 text-right font-mono">{li.quantity ?? "—"}</td>
                    <td className="py-1.5 text-right font-mono">{li.unit_price != null ? `$${li.unit_price.toLocaleString()}` : "—"}</td>
                    <td className="py-1.5 text-right font-mono">{li.amount != null ? `$${li.amount.toLocaleString()}` : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    );
  }

  if (documentType === "financial_statement") {
    return (
      <div>
        <EntityField label="Reporting period" value={entities.reporting_period} />
        <div className="grid grid-cols-2 gap-x-6 mt-2">
          {Object.entries(entities.metrics || {}).map(([k, v]) => (
            <EntityField key={k} label={k.replace(/_/g, " ")} value={`$${Number(v).toLocaleString()}`} />
          ))}
        </div>
      </div>
    );
  }

  // contract / nda / rfp
  const clauses = entities.clauses || {};
  return (
    <div className="space-y-4">
      {Object.entries(clauses).map(([name, clause]) => (
        <div key={name} className="border border-hairline/60 rounded p-3">
          <div className="text-xs font-mono uppercase tracking-wide text-ledger mb-1">{name.replace(/_/g, " ")}</div>
          {clause.days != null && <p className="text-sm">Term: {clause.days} days</p>}
          {clause.notice_days != null && <p className="text-sm">Notice period: {clause.notice_days} days</p>}
          {clause.period_days != null && <p className="text-sm">Period: {clause.period_days} days</p>}
          {clause.period_years != null && <p className="text-sm">Period: {clause.period_years} years</p>}
          {clause.amounts?.length > 0 && <p className="text-sm">Amounts referenced: {clause.amounts.join(", ")}</p>}
          {clause.excerpt && <p className="text-xs text-inkfaint mt-1 italic">"{clause.excerpt.slice(0, 220)}…"</p>}
        </div>
      ))}
      {entities.missing_standard_clauses?.length > 0 && (
        <p className="text-xs text-inkfaint">
          Not detected: {entities.missing_standard_clauses.join(", ").replace(/_/g, " ")}
        </p>
      )}
    </div>
  );
}

export default function DocumentDetail() {
  const { documentId } = useParams();
  const navigate = useNavigate();
  const [document, setDocument] = useState(null);
  const [anomalies, setAnomalies] = useState([]);
  const [crmSync, setCrmSync] = useState(null);
  const [deleting, setDeleting] = useState(false);

  const load = useCallback(async () => {
    const [doc, anoms, sync] = await Promise.all([
      api.getDocument(documentId),
      api.getDocumentAnomalies(documentId),
      api.getCrmSync(documentId),
    ]);
    setDocument(doc);
    setAnomalies(anoms);
    setCrmSync(sync);
  }, [documentId]);

  useEffect(() => { load(); }, [load]);

  const handleDelete = async () => {
    if (!window.confirm(`Delete "${document.filename}"? This removes its extraction results, anomalies, and CRM sync record. This can't be undone.`)) {
      return;
    }
    setDeleting(true);
    try {
      await api.deleteDocument(documentId);
      navigate(`/projects/${document.project_id}`, { replace: true });
    } catch (err) {
      alert(`Couldn't delete document: ${err.message}`);
      setDeleting(false);
    }
  };

  if (!document) return <p className="text-inkfaint text-sm">Loading…</p>;

  const grouped = { critical: [], warning: [], informational: [] };
  for (const a of anomalies) grouped[a.severity]?.push(a);

  return (
    <div>
      <Link to={`/projects/${document.project_id}`} className="font-mono text-xs text-inkfaint hover:text-ledger">
        &larr; Back to project
      </Link>
      <div className="flex items-baseline justify-between mt-2">
        <h1 className="font-display text-3xl font-semibold text-ink">{document.filename}</h1>
        <div className="flex items-center gap-4">
          <span className="font-mono text-xs uppercase tracking-wide text-inkfaint">
            {document.document_type?.replace(/_/g, " ")}
          </span>
          <button
            onClick={handleDelete}
            disabled={deleting}
            className="font-mono text-xs uppercase tracking-wide px-3 py-1.5 rounded border border-critical/40 text-critical hover:bg-critical hover:text-white transition disabled:opacity-50"
          >
            {deleting ? "Deleting…" : "Delete document"}
          </button>
        </div>
      </div>

      {document.low_quality_flag && (
        <div className="mt-3 border border-warn/30 bg-warn/5 rounded-md p-3 text-sm text-warn">
          This document was scanned with low OCR confidence ({document.ocr_confidence?.toFixed(1)}%).
          Extracted values below may contain errors — verify against the original.
        </div>
      )}

      <div className="grid grid-cols-3 gap-6 mt-8">
        <div className="col-span-2 space-y-8">
          <section>
            <h2 className="font-display text-xl text-ink mb-3">Extracted entities</h2>
            <div className="border border-hairline rounded-md p-4 bg-surface">
              <div className="grid grid-cols-2 gap-x-6 mb-3">
                <EntityField label="Parties" value={document.primary_parties} />
                <EntityField label="Jurisdiction" value={document.governing_jurisdiction} />
                <EntityField label="Dates" value={Object.values(document.key_dates || {}).flat()} />
              </div>
              <ExtractionPanel documentType={document.document_type} entities={document.extracted_entities} />
            </div>
          </section>

          <section>
            <h2 className="font-display text-xl text-ink mb-3">Anomalies</h2>
            {anomalies.length === 0 ? (
              <p className="text-sm text-inkfaint">No anomalies detected in this document.</p>
            ) : (
              <div className="space-y-4">
                {["critical", "warning", "informational"].map((sev) =>
                  grouped[sev].length > 0 && (
                    <div key={sev}>
                      {grouped[sev].map((a) => (
                        <div key={a.id} className="flex items-start gap-3 border border-hairline rounded-md p-3 bg-surface mb-2">
                          <SeverityBadge severity={a.severity} />
                          <div>
                            <p className="text-sm text-ink">{a.explanation}</p>
                            {a.evidence && Object.keys(a.evidence).length > 0 && (
                              <details className="mt-2">
                                <summary className="cursor-pointer text-xs font-mono text-inkfaint">View evidence</summary>
                                <pre className="mt-2 text-xs font-mono text-inkfaint whitespace-pre-wrap">{JSON.stringify(a.evidence, null, 2)}</pre>
                              </details>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  )
                )}
              </div>
            )}
          </section>

          <section>
            <h2 className="font-display text-xl text-ink mb-3">CRM sync</h2>
            <CrmSyncPanel documentId={documentId} syncStatus={crmSync} onRetried={load} />
          </section>
        </div>

        <div>
          <h2 className="font-display text-xl text-ink mb-3">Risk score</h2>
          <div className="border border-hairline rounded-md p-4 bg-surface sticky top-6">
            <RiskChart riskScore={document.risk_score} breakdown={document.risk_breakdown?.breakdown} />
          </div>
        </div>
      </div>
    </div>
  );
}
