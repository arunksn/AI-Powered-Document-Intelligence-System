import { useEffect, useState, useRef, useCallback } from "react";
import { useParams, Link } from "react-router-dom";
import { api } from "../api";
import ContradictionCard from "../components/ContradictionCard.jsx";

const STATUS_STYLE = {
  queued: "text-inkfaint bg-hairline/40 border-hairline",
  processing: "text-ledger bg-ledger/10 border-ledger/30",
  complete: "text-ok bg-ok/10 border-ok/30",
  failed: "text-critical bg-critical/10 border-critical/30",
};

export default function ProjectDetail() {
  const { projectId } = useParams();
  const [project, setProject] = useState(null);
  const [documents, setDocuments] = useState([]);
  const [contradictions, setContradictions] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [deletingId, setDeletingId] = useState(null);
  const fileInputRef = useRef(null);

  const load = useCallback(async () => {
    const [proj, docs, contras] = await Promise.all([
      api.getProject(projectId),
      api.listProjectDocuments(projectId),
      api.listContradictions(projectId),
    ]);
    setProject(proj);
    setDocuments(docs);
    setContradictions(contras);
  }, [projectId]);

  useEffect(() => { load(); }, [load]);

  // Keep the project list fresh while documents process. The per-document
  // pipeline itself uses WebSockets; this refresh only keeps project-level
  // document statuses and contradiction results current.
  useEffect(() => {
    const hasActive = documents.some((d) => d.status === "queued" || d.status === "processing");
    if (!hasActive) return;
    const t = setInterval(load, 5000);
    return () => clearInterval(t);
  }, [documents, load]);

  const handleFiles = async (files) => {
    setUploading(true);
    try {
      for (const file of files) {
        await api.uploadDocument(projectId, file);
      }
      await load();
    } finally {
      setUploading(false);
    }
  };

  const handleDelete = async (e, doc) => {
    e.preventDefault();
    e.stopPropagation();
    if (!window.confirm(`Delete "${doc.filename}"? This removes its extraction results, anomalies, and CRM sync record. This can't be undone.`)) {
      return;
    }
    setDeletingId(doc.id);
    try {
      await api.deleteDocument(doc.id);
      await load();
    } catch (err) {
      alert(`Couldn't delete document: ${err.message}`);
    } finally {
      setDeletingId(null);
    }
  };

  const docNames = Object.fromEntries(documents.map((d) => [d.id, d.filename]));

  if (!project) return <p className="text-inkfaint text-sm">Loading…</p>;

  return (
    <div>
      <Link to="/" className="font-mono text-xs text-inkfaint hover:text-ledger">&larr; All projects</Link>
      <h1 className="font-display text-3xl font-semibold text-ink mt-2">{project.name}</h1>
      {project.description && <p className="text-inkfaint text-sm mt-1">{project.description}</p>}

      <div
        className="mt-6 border-2 border-dashed border-hairline rounded-md p-8 text-center bg-surface"
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => {
          e.preventDefault();
          handleFiles(Array.from(e.dataTransfer.files));
        }}
      >
        <p className="text-sm text-inkfaint mb-3">
          Drop PDF, DOCX, XLSX, JPG or PNG files here, or
        </p>
        <button
          onClick={() => fileInputRef.current?.click()}
          disabled={uploading}
          className="font-mono text-xs uppercase tracking-wide px-4 py-2 rounded border border-ledger text-ledger hover:bg-ledger hover:text-white transition disabled:opacity-50"
        >
          {uploading ? "Uploading…" : "Browse files"}
        </button>
        <input
          ref={fileInputRef}
          type="file"
          multiple
          className="hidden"
          accept=".pdf,.docx,.xlsx,.jpg,.jpeg,.png"
          onChange={(e) => handleFiles(Array.from(e.target.files))}
        />
      </div>

      <h2 className="font-display text-xl text-ink mt-10 mb-3">Documents</h2>
      {documents.length === 0 ? (
        <p className="text-sm text-inkfaint">No documents uploaded yet.</p>
      ) : (
        <div className="grid gap-2">
          {documents.map((d) => (
            <div
              key={d.id}
              className="flex items-center justify-between border border-hairline rounded-md p-3 bg-surface hover:border-ledger transition"
            >
              <Link
                to={d.status === "complete" ? `/documents/${d.id}` : `/documents/${d.id}/processing`}
                className="flex-1 min-w-0"
              >
                <span className="font-body text-sm text-ink">{d.filename}</span>
                {d.document_type && (
                  <span className="ml-2 font-mono text-xs text-inkfaint uppercase">{d.document_type.replace(/_/g, " ")}</span>
                )}
                {d.low_quality_flag && (
                  <span className="ml-2 font-mono text-xs text-warn uppercase">low OCR confidence</span>
                )}
              </Link>
              <div className="flex items-center gap-3 shrink-0">
                {d.risk_score != null && d.status === "complete" && (
                  <span className="font-mono text-xs text-inkfaint">risk {Math.round(d.risk_score)}</span>
                )}
                <span className={`px-2 py-0.5 rounded border text-xs font-mono uppercase tracking-wide ${STATUS_STYLE[d.status]}`}>
                  {d.status}
                </span>
                <button
                  onClick={(e) => handleDelete(e, d)}
                  disabled={deletingId === d.id}
                  title="Delete document"
                  className="font-mono text-xs uppercase tracking-wide text-inkfaint hover:text-critical transition disabled:opacity-50 px-1"
                >
                  {deletingId === d.id ? "…" : "Delete"}
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      <h2 className="font-display text-xl text-ink mt-10 mb-3">Cross-document contradictions</h2>
      {documents.filter((d) => d.status === "complete").length < 2 ? (
        <p className="text-sm text-inkfaint">
          Contradiction detection runs once at least two documents in this project have finished processing.
        </p>
      ) : contradictions.length === 0 ? (
        <p className="text-sm text-inkfaint">No contradictions detected across this project's documents.</p>
      ) : (
        <div className="grid gap-3">
          {contradictions.map((c) => (
            <ContradictionCard key={c.id} contradiction={c} docNames={docNames} />
          ))}
        </div>
      )}
    </div>
  );
}
