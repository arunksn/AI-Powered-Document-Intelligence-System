import { useEffect, useState, useCallback } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import { api } from "../api";
import { useDocumentSocket } from "../ws.js";
import StageCard from "../components/StageCard.jsx";
import SeverityBadge from "../components/SeverityBadge.jsx";

const STAGE_ORDER = [0, 1, 2, 3, 4, 5];

function renderStageOutput(stageNumber, output) {
  if (!output) return null;
  if (stageNumber === 0) {
    return (
      <div className="text-sm space-y-1">
        <p><span className="text-inkfaint">Scanned document:</span> {output.is_scanned ? "yes" : "no"}</p>
        {output.is_scanned && (
          <p><span className="text-inkfaint">OCR confidence:</span> {output.ocr_confidence?.toFixed(1)}%</p>
        )}
        {output.low_quality_flag && <p className="text-warn">Flagged as low-quality scan.</p>}
        <p><span className="text-inkfaint">Structure found:</span> {output.sections_found} sections, {output.tables_found} tables</p>
      </div>
    );
  }
  if (stageNumber === 1) {
    return (
      <div className="text-sm space-y-1">
        <p><span className="text-inkfaint">Type:</span> {output.document_type?.replace(/_/g, " ")}</p>
        <p><span className="text-inkfaint">Parties:</span> {(output.primary_parties || []).join(", ") || "none detected"}</p>
        {output.governing_jurisdiction && <p><span className="text-inkfaint">Jurisdiction:</span> {output.governing_jurisdiction}</p>}
      </div>
    );
  }
  if (stageNumber === 3) {
    const anomalies = output.anomalies || [];
    if (anomalies.length === 0) return <p className="text-sm text-inkfaint">No anomalies detected.</p>;
    return (
      <div className="space-y-2">
        {anomalies.map((a, i) => (
          <div key={i} className="flex items-start gap-2">
            <SeverityBadge severity={a.severity} />
            <p className="text-sm text-ink">{a.explanation}</p>
          </div>
        ))}
      </div>
    );
  }
  if (stageNumber === 4) {
    return (
      <p className="text-sm">
        <span className="font-display text-2xl text-ink mr-2">{Math.round(output.risk_score)}</span>
        <span className="text-inkfaint">/ 100 overall risk</span>
      </p>
    );
  }
  if (stageNumber === 5) {
    return (
      <p className="text-sm">
        Compared <span className="font-mono">{output.documents_compared || 0}</span> documents and found
        <span className="font-mono mx-1">{output.contradiction_count || 0}</span> contradiction(s).
      </p>
    );
  }
  return (
    <pre className="text-xs font-mono text-inkfaint whitespace-pre-wrap break-words">
      {JSON.stringify(output, null, 2)}
    </pre>
  );
}

export default function DocumentProcessing() {
  const { documentId } = useParams();
  const navigate = useNavigate();
  const [document, setDocument] = useState(null);
  const [stages, setStages] = useState({});

  const load = useCallback(async () => {
    const [doc, stageRows] = await Promise.all([
      api.getDocument(documentId),
      api.getDocumentStages(documentId),
    ]);
    setDocument(doc);
    const map = {};
    for (const s of stageRows) map[s.stage_number] = s;
    setStages(map);
  }, [documentId]);

  useEffect(() => { load(); }, [load]);

  useDocumentSocket(documentId, (msg) => {
    if (msg.type === "stage_update") {
      setStages((prev) => ({
        ...prev,
        [msg.stage_number]: {
          stage_number: msg.stage_number,
          stage_name: msg.stage_name,
          status: msg.status,
          output: msg.output ?? prev[msg.stage_number]?.output,
        },
      }));
    }
    if (msg.type === "status") {
      setDocument((prev) => (prev ? { ...prev, status: msg.status, error_message: msg.error || prev.error_message } : prev));
    }
  });

  if (!document) return <p className="text-inkfaint text-sm">Loading…</p>;

  return (
    <div>
      <Link to={`/projects/${document.project_id}`} className="font-mono text-xs text-inkfaint hover:text-ledger">
        &larr; Back to project
      </Link>
      <h1 className="font-display text-3xl font-semibold text-ink mt-2">{document.filename}</h1>
      <p className="text-inkfaint text-sm mt-1">
        Processing pipeline — each stage streams its result as soon as it finishes.
      </p>

      {document.status === "failed" && (
        <div className="mt-4 border border-critical/30 bg-critical/5 rounded-md p-4 text-sm text-critical flex items-center justify-between">
          <div>
            <p className="font-semibold">Processing Failed</p>
            <p className="mt-0.5">{document.error_message || "An unexpected error occurred during processing."}</p>
          </div>
          <button
            type="button"
            onClick={async () => {
              try {
                await api.reprocessDocument(documentId);
                setDocument((prev) => ({ ...prev, status: "queued", error_message: null }));
                setStages({});
                load();
              } catch (err) {
                alert("Failed to reprocess: " + err.message);
              }
            }}
            className="font-mono text-xs uppercase tracking-wide px-3 py-1.5 rounded bg-critical text-white hover:bg-critical/80 transition"
          >
            Retry Processing
          </button>
        </div>
      )}

      {document.status === "complete" && (
        <div className="mt-5 flex items-center justify-between border border-ok/20 bg-ok/5 rounded-md p-3">
          <p className="text-sm text-ink">Processing is complete. You can review the full document intelligence report.</p>
          <button
            onClick={() => navigate(`/documents/${documentId}`)}
            className="font-mono text-xs uppercase tracking-wide px-3 py-1.5 rounded bg-ledger text-white hover:bg-ledgerlight transition"
          >
            Open report
          </button>
        </div>
      )}


      <div className="mt-8">
        {STAGE_ORDER.map((num) => {
          const stage = stages[num] || { stage_name: defaultStageName(num), status: "pending" };
          return (
            <StageCard
              key={num}
              stageNumber={num}
              stageName={stage.stage_name}
              status={stage.status}
              output={stage.output}
              renderOutput={(output) => renderStageOutput(num, output)}
            />
          );
        })}
      </div>
    </div>
  );
}

function defaultStageName(num) {
  return ["Ingestion & Normalisation", "Document Classification", "Entity & Clause Extraction", "Anomaly Detection", "Risk Scoring", "Cross-Document Contradiction Check"][num];
}
