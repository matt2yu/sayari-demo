import type { Chain, Persona, ProductDetail } from "../types";

/** Renders one resolved traversal path as a chain of hops. */
function ChainView({ chain }: { chain: Chain }) {
  return (
    <ol className="chain">
      {chain.hops.map((hop) => (
        <li key={`${hop.hop}-${hop.id}`} className={hop.sanctioned ? "hop hot" : "hop"}>
          <span className="edge">{hop.edge}</span>
          <span className="node">{hop.label}</span>
          {hop.countries.length > 0 && (
            <span className="cc">{hop.countries.slice(0, 4).join(", ")}</span>
          )}
          {hop.sanctioned && <span className="badge">sanctioned</span>}
        </li>
      ))}
    </ol>
  );
}

export function DetailPanel({
  detail,
  persona,
  personas,
  onClose,
}: {
  detail: ProductDetail;
  persona: string;
  personas: Persona[];
  onClose: () => void;
}) {
  const verdict = detail.verdicts[persona];
  const seed = detail.flags.filter((f) => f.risk_type === "seed");
  const network = detail.flags.filter((f) => f.risk_type !== "seed");
  const ownership = detail.flags.flatMap((f) =>
    (f.chains ?? [])
      .filter((c) => c.kind === "ownership")
      .map((c) => ({ flag: f, chain: c })),
  );

  return (
    <div className="overlay" onClick={onClose}>
      <aside className="panel" onClick={(e) => e.stopPropagation()}>
        <button className="close" onClick={onClose} aria-label="Close">
          ×
        </button>

        <h2>
          {detail.brand} <small>{detail.product}</small>
        </h2>
        <p className="legal">
          {detail.legal_name} · {detail.country}
          {detail.parent && ` · parent ${detail.parent}`}
        </p>

        {/* 1. The verdict, for every buyer at once. The row is the argument. */}
        <section>
          <h3>Who is restricted</h3>
          <table className="verdicts">
            <tbody>
              {personas.map((p) => {
                const v = detail.verdicts[p.key];
                return (
                  <tr key={p.key} className={p.key === persona ? "current" : ""}>
                    <th>{p.label}</th>
                    <td>
                      <span className={`chip ${v.status}`}>
                        {v.status.replace("_", " ")}
                      </span>
                    </td>
                    <td className="reasoncell">
                      {v.reasons.length > 0 ? v.headline : "—"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>

          {verdict.reasons.map((reason) => (
            <div className="reason" key={reason.authority + reason.detail}>
              <b>{reason.authority}</b>
              <div>{reason.detail}</div>
              <div className="cite">
                Binds {reason.binds} · {reason.citation}
              </div>
            </div>
          ))}

          {verdict.coverage_warning && (
            <p className="warn">{verdict.coverage_warning}</p>
          )}
        </section>

        {/* 2. Ownership. The EZVIZ case: on no list itself, three hops from CETC. */}
        {ownership.length > 0 && (
          <section>
            <h3>Ownership chains</h3>
            <p className="hint">
              Derived by traversing the graph. These describe a relationship, not a
              property of the brand.
            </p>
            {ownership.slice(0, 4).map(({ flag, chain }, i) => (
              <div className="chainblock" key={`${flag.id}-${i}`}>
                <div className="flagname">
                  {flag.label ?? flag.id}{" "}
                  <span className={`lvl ${flag.level}`}>{flag.level}</span>
                </div>
                <ChainView chain={chain} />
              </div>
            ))}
          </section>
        )}

        {/* 3. Seed vs network is the distinction that keeps this honest. */}
        <section>
          <h3>Risk flags</h3>
          {seed.length > 0 && (
            <>
              <h4>On this entity itself ({seed.length})</h4>
              {seed.map((flag) => (
                <div className="flag" key={flag.id}>
                  <b>{flag.label ?? flag.id}</b>{" "}
                  <span className={`lvl ${flag.level}`}>{flag.level}</span>
                  <p>{flag.description}</p>
                  {flag.sources.length > 0 && (
                    <div className="cite">Source: {flag.sources.join("; ")}</div>
                  )}
                </div>
              ))}
            </>
          )}
          {network.length > 0 && (
            <>
              <h4>Derived through relationships ({network.length})</h4>
              {network.map((flag) => (
                <div className="flag" key={flag.id}>
                  <b>{flag.label ?? flag.id}</b>{" "}
                  <span className={`lvl ${flag.level}`}>{flag.level}</span>
                  <p>{flag.description}</p>
                </div>
              ))}
            </>
          )}
          {detail.flags.length === 0 && <p className="hint">No reportable flags.</p>}
        </section>

        {/* 4. The adjudication is part of the deliverable, not an appendix. */}
        <section>
          <h3>How we know</h3>
          <h4>Entities screened ({detail.family.length})</h4>
          <ul className="family">
            {detail.family.map((member) => (
              <li key={member.id}>
                {member.translated_label ?? member.label}
                <span className="via">{member.via}</span>
                {member.sent + member.received > 0 && (
                  <span className="cc">
                    {(member.sent + member.received).toLocaleString()} shipments
                  </span>
                )}
              </li>
            ))}
          </ul>

          {detail.rejected.length > 0 && (
            <>
              <h4>Candidates rejected ({detail.rejected.length})</h4>
              <ul className="rejected">
                {detail.rejected.slice(0, 8).map((r) => (
                  <li key={r.id}>
                    <span className="label">{r.label}</span>
                    <span className="reason">{r.rejected_because}</span>
                  </li>
                ))}
              </ul>
            </>
          )}

          {detail.dropped_flags.length > 0 && (
            <>
              <h4>Flags excluded ({detail.dropped_flags.length})</h4>
              <p className="hint">
                Returned by the API but deprecated in Sayari's ontology, so not used
                to support any finding.
              </p>
              <ul className="rejected">
                {detail.dropped_flags.slice(0, 6).map((f) => (
                  <li key={f.id}>
                    <span className="label">{f.id}</span>
                    <span className="reason">{f.dropped_because}</span>
                  </li>
                ))}
              </ul>
            </>
          )}

          {detail.context_flags.length > 0 && (
            <>
              <h4>Country context ({detail.context_flags.length})</h4>
              <p className="hint">
                Jurisdiction indicators, not allegations about this company. Note the
                Corruption Perceptions Index runs 0–100 with 100 as cleanest.
              </p>
              <ul className="rejected">
                {detail.context_flags.map((f) => (
                  <li key={f.id}>
                    <span className="label">{f.label ?? f.id}</span>
                  </li>
                ))}
              </ul>
            </>
          )}
        </section>
      </aside>
    </div>
  );
}
