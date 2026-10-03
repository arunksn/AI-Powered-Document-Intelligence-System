import { useState, useEffect } from "react";

function StageMark({ status }) {
  if (status === "complete") {
    return (
      <div className="w-8 h-8 rounded-full border-2 border-ok flex items-center justify-center bg-ok/10 stamp-tick text-ok font-bold">
        <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
          <path d="M2 7L5.5 10.5L12 3" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </div>
    );
  }
  if (status === "active") {
    return (
      <div className="w-8 h-8 rounded-full border-2 border-ledger flex items-center justify-center bg-ledger/5">
        <div className="w-3.5 h-3.5 rounded-full border-2 border-ledger border-t-transparent animate-spin" />
      </div>
    );
  }
  if (status === "skipped") {
    return (
      <div className="w-8 h-8 rounded-full border-2 border-hairline flex items-center justify-center bg-hairline/20">
        <span className="text-inkfaint text-xs font-bold">—</span>
      </div>
    );
  }
  if (status === "failed") {
    return (
      <div className="w-8 h-8 rounded-full border-2 border-critical flex items-center justify-center bg-critical/10">
        <span className="text-critical text-sm font-bold">!</span>
      </div>
    );
  }
  return <div className="w-8 h-8 rounded-full border-2 border-hairline bg-paper" />;
}

export default function StageCard({ stageNumber, stageName, status, output, renderOutput }) {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (status === "active" || status === "complete" || status === "failed") {
      setOpen(true);
    }
  }, [status]);

  const hasContent = Boolean(output) || status === "complete" || status === "skipped" || status === "failed";

  return (
    <div className="flex gap-4">
      <div className="flex flex-col items-center">
        <StageMark status={status} />
        <div className="flex-1 w-px bg-hairline mt-1" />
      </div>
      <div className="flex-1 pb-6">
        <button
          type="button"
          onClick={() => hasContent && setOpen((o) => !o)}
          className={`w-full text-left flex items-center justify-between group ${hasContent ? "cursor-pointer" : "cursor-default"}`}
        >
          <div>
            <span className="font-mono text-xs text-inkfaint mr-2">
              {String(stageNumber).padStart(2, "0")}
            </span>
            <span className={`font-display text-lg ${status === "complete" ? "text-ink font-semibold" : status === "active" ? "text-ledger font-medium" : status === "failed" ? "text-critical" : "text-inkfaint"}`}>
              {stageName}
            </span>
          </div>
          {hasContent && (
            <span className="font-mono text-xs text-inkfaint group-hover:text-ledger transition">
              {open ? "hide [-]" : "show [+]"}
            </span>
          )}
        </button>
        {status === "active" && (
          <p className="mt-1 text-sm text-ledger font-mono animate-pulse">Processing stage outputs…</p>
        )}
        {status === "skipped" && (
          <p className="mt-1 text-sm text-inkfaint">This project needs at least two completed documents for this stage.</p>
        )}
        {status === "failed" && (
          <p className="mt-1 text-sm text-critical font-medium">Stage processing encountered an issue.</p>
        )}
        {open && hasContent && (
          <div className="mt-3 border border-hairline rounded-md bg-surface p-4 transition-all">
            {renderOutput ? renderOutput(output) : (
              <pre className="text-xs font-mono text-ink whitespace-pre-wrap break-words">
                {JSON.stringify(output, null, 2)}
              </pre>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

