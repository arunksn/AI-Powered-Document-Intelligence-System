import { Link } from "react-router-dom";

export default function ContradictionCard({ contradiction, docNames }) {
  return (
    <div className="border border-warn/30 bg-warn/5 rounded-md p-4">
      <div className="font-mono text-xs uppercase tracking-wide text-warn mb-2">
        {contradiction.field.replace(/_/g, " ")}
      </div>
      <p className="text-sm text-ink mb-3">{contradiction.explanation}</p>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div className="bg-surface border border-hairline rounded p-3">
          <Link to={`/documents/${contradiction.document_a_id}`} className="text-xs font-mono text-ledger hover:underline">
            {docNames[contradiction.document_a_id] || contradiction.document_a_id.slice(0, 8)}
          </Link>
          <div className="font-display text-lg mt-1 break-words">{contradiction.value_a}</div>
        </div>
        <div className="bg-surface border border-hairline rounded p-3">
          <Link to={`/documents/${contradiction.document_b_id}`} className="text-xs font-mono text-ledger hover:underline">
            {docNames[contradiction.document_b_id] || contradiction.document_b_id.slice(0, 8)}
          </Link>
          <div className="font-display text-lg mt-1 break-words">{contradiction.value_b}</div>
        </div>
      </div>
    </div>
  );
}
