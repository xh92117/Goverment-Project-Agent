export default function Loading() {
  return (
    <div className="workspace-loading" role="status" aria-live="polite">
      <div className="workspace-loading-card">
        <span className="workspace-loading-spinner" />
        <span>正在加载...</span>
      </div>
    </div>
  );
}
