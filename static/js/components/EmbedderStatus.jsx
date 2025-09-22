import React from "react";

const clamp = (value) => Math.max(0, Math.min(100, Number.isFinite(value) ? value : 0));

export function EmbedderStatus({
  status,
  onRetry,
  onUseFallback,
  onStart,
}) {
  const state = status?.state || "unknown";
  const model = status?.model || "embeddinggemma";
  const progress = clamp(status?.progress ?? 0);
  const fallbacks = Array.isArray(status?.fallbacks)
    ? status.fallbacks.filter(Boolean)
    : [];
  const message = (() => {
    switch (state) {
      case "ready":
        return `Ready: ${model}`;
      case "installing":
        return `Installing ${model}… ${progress}%`;
      case "missing":
        return `Model ${model} is not installed yet.`;
      case "absent":
        return "Automatic installation is disabled.";
      case "error":
        return status?.detail || status?.error || `Unable to prepare ${model}.`;
      default:
        return "Checking Ollama…";
    }
  })();

  const showRetry = state === "error" || state === "missing";
  const showStart = status?.error === "ollama_offline" || status?.ollama?.alive === false;
  const showFallbacks = fallbacks.length > 0 && state === "error";

  return (
    <section className="embedder-status" aria-busy={state === "installing"}>
      <div className="embedder-header">
        <h2>Embedding model</h2>
        <p>{message}</p>
      </div>
      {state === "installing" ? (
        <div className="embedder-progress" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={progress}>
          <div style={{ width: `${progress}%` }}>{progress}%</div>
        </div>
      ) : null}
      <div className="embedder-actions">
        {showRetry ? (
          <button type="button" onClick={onRetry} disabled={state === "installing"}>
            Retry
          </button>
        ) : null}
        {showFallbacks ? (
          <FallbackPicker options={fallbacks} onUseFallback={onUseFallback} disabled={state === "installing"} />
        ) : null}
        {showStart ? (
          <button type="button" onClick={onStart} disabled={state === "installing"}>
            Start Ollama
          </button>
        ) : null}
      </div>
      <p className="embedder-help">
        We'll install <code>embeddinggemma</code> automatically. Manual command:
        <code>ollama pull embeddinggemma</code>
      </p>
    </section>
  );
}

function FallbackPicker({ options, onUseFallback, disabled }) {
  const [selection, setSelection] = React.useState(options[0] || "");
  const handleApply = React.useCallback(() => {
    if (selection && onUseFallback) {
      onUseFallback(selection);
    }
  }, [selection, onUseFallback]);

  React.useEffect(() => {
    if (!options.includes(selection)) {
      setSelection(options[0] || "");
    }
  }, [options, selection]);

  return (
    <div className="fallback-group">
      <label htmlFor="embedder-fallback-select">Use fallback</label>
      <select
        id="embedder-fallback-select"
        value={selection}
        onChange={(event) => setSelection(event.target.value)}
        disabled={disabled || options.length === 0}
      >
        {options.map((option) => (
          <option key={option} value={option}>
            {option}
          </option>
        ))}
      </select>
      <button type="button" onClick={handleApply} disabled={disabled || !selection}>
        Apply
      </button>
    </div>
  );
}

export default EmbedderStatus;
