import "./PoliciesView.css";

export function PoliciesView() {
  return (
    <section className="registry-view">
      <div className="registry-view__header"><div><p className="eyebrow">Governing rules</p><h2>Policy registry</h2></div><span className="mini-state mini-state--active">Current</span></div>
      <div className="registry-table">
        <div className="registry-row registry-row--header"><span>Policy</span><span>Domain</span><span>Rules</span><span>State</span></div>
        <div className="registry-row"><strong>CMS-SNF-100</strong><span>Post-acute skilled nursing</span><span>3 constraints</span><span className="mini-state mini-state--active">Active</span></div>
      </div>
    </section>
  );
}
