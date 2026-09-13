import { AnimatePresence, motion } from "framer-motion";
import {
  AlertTriangle,
  BadgeAlert,
  ArrowRight,
  Check,
  ExternalLink,
  Info,
  Scale,
  Ship,
  X,
} from "lucide-react";
import type { Chain, Persona, ProductDetail } from "../types";
import { STATUS } from "../status";
import { logoFor } from "../brands";
import { LISTING_EFFECT } from "../risk";

function Section({
  icon: Icon,
  title,
  hint,
  children,
}: {
  icon: typeof Info;
  title: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="border-t border-line px-6 py-5">
      <div className="mb-3 flex items-center gap-2">
        <Icon size={14} className="text-faint" />
        <h3 className="text-xs font-semibold uppercase tracking-wider text-muted">
          {title}
        </h3>
      </div>
      {hint && <p className="mb-3 text-xs leading-relaxed text-faint">{hint}</p>}
      {children}
    </section>
  );
}

/** One ownership path, rendered as a chain rather than a list, so the distance
 *  from the brand to the listed party is visible rather than implied. */
function ChainView({ chain }: { chain: Chain }) {
  return (
    <ol className="space-y-0">
      {chain.hops
        .filter((hop) => hop.label)
        .map((hop, i) => (
          <li key={`${hop.hop}-${hop.id}`} className="relative pl-5">
            <span className="absolute left-0 top-2.5 h-2 w-2 rounded-full bg-line" />
            {i > 0 && (
              <span className="absolute left-[3px] top-0 h-2.5 w-px bg-line" />
            )}
            <span className="absolute left-[3px] top-4.5 h-[calc(100%-1rem)] w-px bg-line" />
            <div className="pb-3">
              <div className="font-mono text-[10px] text-faint">{hop.edge}</div>
              <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                <span className="text-sm text-fg">{hop.label}</span>
                {hop.countries.length > 0 && (
                  <span className="text-[10px] text-faint">
                    {hop.countries.slice(0, 3).join(" · ")}
                  </span>
                )}
                {hop.sanctioned && (
                  <span className="rounded border border-stop/45 bg-stop/10 px-1.5 py-px text-[10px] uppercase text-stop">
                    sanctioned
                  </span>
                )}
              </div>
            </div>
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
  // A seed flag means the entity is on the list itself, with nothing in between.
  // That is the strongest evidence in the dataset, but it has no chain to draw,
  // so without its own block it reads as weaker than an inherited listing purely
  // because there is less to look at. TP-Link is exactly this case.
  const directListings = detail.flags.filter(
    (f) =>
      f.risk_type === "seed" &&
      detail.regime_hits.some(
        (h) => h.how === "seed_risk" && h.factor === f.id,
      ),
  );
  const ownership = detail.flags.flatMap((f) =>
    (f.chains ?? [])
      .filter((c) => c.kind === "ownership" && c.hops.some((h) => h.label))
      .map((c) => ({ flag: f, chain: c })),
  );
  const logo = logoFor(detail.id);

  return (
    <AnimatePresence>
      <motion.div
        className="fixed inset-0 z-50 flex justify-end bg-black/65 backdrop-blur-sm"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        onClick={onClose}
      >
        <motion.aside
          className="h-full w-full max-w-2xl overflow-y-auto border-l border-line bg-surface"
          initial={{ x: 40, opacity: 0 }}
          animate={{ x: 0, opacity: 1 }}
          transition={{ type: "spring", stiffness: 260, damping: 30 }}
          onClick={(e) => e.stopPropagation()}
        >
          <header className="sticky top-0 z-10 flex items-start gap-3 border-b border-line bg-surface/95 px-6 py-4 backdrop-blur">
            {logo && (
              <img
                src={logo}
                alt=""
                className="h-10 w-10 rounded-lg bg-white/95 object-contain p-1"
              />
            )}
            <div className="min-w-0 flex-1">
              <h2 className="text-lg font-semibold leading-tight text-fg">
                {detail.brand}{" "}
                <span className="font-normal text-muted">{detail.product}</span>
              </h2>
              <p className="truncate text-xs text-faint">
                {detail.legal_name} · {detail.country}
                {detail.parent && ` · parent ${detail.parent}`}
              </p>
            </div>
            <button
              onClick={onClose}
              aria-label="Close"
              className="rounded-lg p-1.5 text-faint hover:bg-raised hover:text-fg"
            >
              <X size={18} />
            </button>
          </header>

          {/* The verdict matrix. All four buyers at once, because the contrast
              between rows is the finding. */}
          <Section icon={Scale} title="Who is restricted">
            <div className="overflow-hidden rounded-lg border border-line">
              {personas.map((p) => {
                const v = detail.verdicts[p.key];
                const style = STATUS[v.status];
                const current = p.key === persona;
                return (
                  <div
                    key={p.key}
                    className={[
                      "flex items-center gap-3 border-b border-line px-3 py-2.5 last:border-0",
                      current ? "bg-raised" : "",
                    ].join(" ")}
                  >
                    <span
                      className={`h-2 w-2 shrink-0 rounded-full ${style.dot}`}
                    />
                    <span
                      className={[
                        "w-36 shrink-0 text-sm",
                        current ? "font-semibold text-fg" : "text-muted",
                      ].join(" ")}
                    >
                      {p.label}
                    </span>
                    <span className={`text-xs ${style.text}`}>
                      {style.label}
                    </span>
                  </div>
                );
              })}
            </div>

            {verdict.reasons.map((reason) => (
              <div
                key={reason.authority + reason.detail}
                className="mt-3 rounded-lg border border-line bg-ink/40 p-3"
              >
                <div className="text-sm font-medium text-fg">
                  {reason.authority}
                </div>
                <p className="mt-1 text-xs leading-relaxed text-muted">
                  {reason.detail}
                </p>
                <p className="mt-1.5 text-[10px] text-faint">
                  Binds {reason.binds} · {reason.citation}
                </p>
              </div>
            ))}

            {verdict.coverage_warning && (
              <p className="mt-3 flex gap-2 rounded-lg border border-check/30 bg-check/8 p-3 text-xs leading-relaxed text-check">
                <AlertTriangle size={14} className="mt-px shrink-0" />
                {verdict.coverage_warning}
              </p>
            )}
          </Section>

          {directListings.length > 0 && (
            <Section
              icon={BadgeAlert}
              title="Listed directly"
              hint="The entity is named on the list itself. Nothing is inferred and no relationship is traversed, which is what makes this a prohibition rather than a risk signal."
            >
              {directListings.map((flag) => {
                const carriers = detail.family.filter((m) =>
                  flag.carried_by.includes(m.id),
                );
                const hit = detail.regime_hits.find(
                  (h) => h.how === "seed_risk" && h.factor === flag.id,
                );
                const effect = hit ? LISTING_EFFECT[hit.regime] : undefined;
                return (
                  <div
                    key={flag.id}
                    className="mb-3 rounded-lg border border-stop/35 bg-stop/5 p-3 last:mb-0"
                  >
                    {/* The badge states what the listing DOES, not that it
                        exists -- the paragraph already says the entity is on the
                        list. Sayari's severity level is deliberately absent here:
                        "high" appears on unrestricted products throughout the
                        grid, so showing it beside a prohibition would imply the
                        severity scale decides the verdict. It does not. */}
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-sm font-medium text-fg">
                        {flag.label ?? flag.id}
                      </span>
                      {effect && (
                        <span className="rounded border border-stop/45 bg-stop/10 px-1.5 py-px text-[10px] uppercase tracking-wide text-stop">
                          {effect.badge}
                        </span>
                      )}
                    </div>

                    {carriers.map((m) => (
                      <p key={m.id} className="mt-2 text-xs text-fg">
                        {m.label}
                        {m.translated_label && m.translated_label !== m.label && (
                          <span className="text-faint"> · {m.translated_label}</span>
                        )}
                        <span className="text-faint">
                          {" "}
                          · {m.countries.slice(0, 3).join(", ")}
                        </span>
                      </p>
                    ))}

                    {effect && (
                      <p
                        className={`mt-2 text-xs leading-relaxed ${
                          effect.isSanction ? "text-stop" : "text-check"
                        }`}
                      >
                        {effect.effect}
                      </p>
                    )}
                    {flag.description && (
                      <p className="mt-2 text-[11px] leading-relaxed text-faint">
                        {flag.description}
                      </p>
                    )}
                    {flag.sources.length > 0 && (
                      <p className="mt-1.5 text-[10px] text-faint">
                        Source: {flag.sources.join("; ")}
                      </p>
                    )}
                  </div>
                );
              })}
            </Section>
          )}

          {ownership.length > 0 && (
            <Section
              icon={ArrowRight}
              title="Ownership"
              hint="Reconstructed by traversing corporate registries. These describe a relationship, not a property of the brand."
            >
              {ownership.slice(0, 4).map(({ flag, chain }, i) => (
                <div key={`${flag.id}-${i}`} className="mb-4 last:mb-0">
                  <div className="mb-2 flex items-center gap-2">
                    <span className="text-xs text-muted">
                      {flag.label ?? flag.id}
                    </span>
                    {flag.level && (
                      <span className="rounded border border-line px-1.5 py-px text-[10px] uppercase text-faint">
                        {flag.level}
                      </span>
                    )}
                  </div>
                  <ChainView chain={chain} />
                </div>
              ))}
            </Section>
          )}

          {detail.sanctioned_trade?.length > 0 && (
            <Section
              icon={Ship}
              title="Trade with sanctioned parties"
              hint="Every shipment between this brand's entities and the counterparty, dated against that party's designation. Trade predating a designation was lawful at the time."
            >
              {detail.sanctioned_trade.map((f) => (
                <div
                  key={f.id}
                  className="mb-3 rounded-lg border border-line bg-ink/40 p-3 last:mb-0"
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-mono text-[10px] text-faint">
                      {f.edge}
                    </span>
                    <span className="text-sm text-fg">{f.label}</span>
                    <span className="text-[10px] text-faint">
                      {f.countries.join(" · ")}
                    </span>
                  </div>

                  <div className="mt-2.5 flex gap-5">
                    <div>
                      <div
                        className={`text-xl font-semibold tabular-nums ${
                          f.count_after > 0 ? "text-stop" : "text-clear"
                        }`}
                      >
                        {f.count_after.toLocaleString()}
                      </div>
                      <div className="text-[10px] text-faint">
                        on/after designation
                      </div>
                    </div>
                    <div>
                      <div className="text-xl font-semibold tabular-nums text-muted">
                        {f.count_before.toLocaleString()}
                      </div>
                      <div className="text-[10px] text-faint">before</div>
                    </div>
                  </div>

                  <p
                    className={`mt-2 text-xs leading-relaxed ${
                      f.count_after > 0 ? "text-stop" : "text-clear"
                    }`}
                  >
                    {f.assessment}
                  </p>

                  <p className="mt-2 text-[10px] leading-relaxed text-faint">
                    {f.examined.toLocaleString()} of{" "}
                    {f.shipment_total.toLocaleString()} examined
                    {f.complete && " (complete)"}
                    {f.designated_on && ` · designated ${f.designated_on}`}
                  </p>

                  <p
                    className={`mt-1 flex items-start gap-1.5 text-[10px] leading-relaxed ${
                      f.ofac_sdn_confirmed ? "text-clear" : "text-faint"
                    }`}
                  >
                    {f.ofac_sdn_confirmed && (
                      <Check size={11} className="mt-px shrink-0" />
                    )}
                    {f.corroboration}
                  </p>
                </div>
              ))}
            </Section>
          )}

          <Section
            icon={Info}
            title="Risk flags"
            hint="Sayari's own wording, hedges intact. Flags on the entity itself are kept apart from flags derived by traversing the graph."
          >
            {seed.length > 0 && (
              <>
                <h4 className="mb-2 text-[11px] font-semibold text-muted">
                  On this entity ({seed.length})
                </h4>
                {seed.map((flag) => (
                  <FlagRow key={flag.id} flag={flag} />
                ))}
              </>
            )}
            {network.length > 0 && (
              <>
                <h4 className="mb-2 mt-4 text-[11px] font-semibold text-muted">
                  Derived through relationships ({network.length})
                </h4>
                {network.slice(0, 8).map((flag) => (
                  <FlagRow key={flag.id} flag={flag} />
                ))}
                {network.length > 8 && (
                  <p className="mt-2 text-[11px] text-faint">
                    +{network.length - 8} more
                  </p>
                )}
              </>
            )}
            {detail.flags.length === 0 && (
              <p className="text-xs text-faint">No reportable flags.</p>
            )}
          </Section>

          <Section
            icon={ExternalLink}
            title="How we know"
            hint="Screening is only as good as the match behind it, so the adjudication is published rather than hidden."
          >
            <h4 className="mb-2 text-[11px] font-semibold text-muted">
              Entities screened ({detail.family.length})
            </h4>
            <ul className="space-y-1">
              {detail.family.map((m) => (
                <li
                  key={m.id}
                  className="flex flex-wrap items-baseline gap-x-2 border-b border-line/60 pb-1 text-xs text-muted last:border-0"
                >
                  <span className="text-fg">
                    {m.translated_label ?? m.label}
                  </span>
                  <span className="rounded bg-ink px-1 text-[10px] uppercase text-faint">
                    {m.via}
                  </span>
                  {m.sent + m.received > 0 && (
                    <span className="text-[10px] text-faint">
                      {(m.sent + m.received).toLocaleString()} shipments
                    </span>
                  )}
                </li>
              ))}
            </ul>

            {detail.rejected.length > 0 && (
              <>
                <h4 className="mb-2 mt-4 text-[11px] font-semibold text-muted">
                  Candidates rejected ({detail.rejected.length})
                </h4>
                <ul className="space-y-1">
                  {detail.rejected.slice(0, 6).map((r) => (
                    <li key={r.id} className="text-xs">
                      <span className="text-muted">{r.label}</span>
                      <span className="text-faint"> — {r.rejected_because}</span>
                    </li>
                  ))}
                </ul>
              </>
            )}

            {detail.dropped_flags.length > 0 && (
              <p className="mt-4 text-[11px] leading-relaxed text-faint">
                {detail.dropped_flags.length} flags were returned by the API but
                excluded as deprecated in Sayari's ontology, so none of them
                supports a finding here.
              </p>
            )}
          </Section>
        </motion.aside>
      </motion.div>
    </AnimatePresence>
  );
}

function FlagRow({ flag }: { flag: ProductDetail["flags"][number] }) {
  return (
    <div className="mb-2.5 last:mb-0">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs font-medium text-fg">
          {flag.label ?? flag.id}
        </span>
        {flag.level && (
          <span className="rounded border border-line px-1.5 py-px text-[10px] uppercase text-faint">
            {flag.level}
          </span>
        )}
      </div>
      {flag.description && (
        <p className="mt-0.5 text-[11px] leading-relaxed text-faint">
          {flag.description}
        </p>
      )}
    </div>
  );
}
