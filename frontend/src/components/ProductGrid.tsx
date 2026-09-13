import { AnimatePresence, motion } from "framer-motion";
import { AlertTriangle, Flag } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import type { ProductCard } from "../types";
import { ORDER, STATUS } from "../status";
import { logoFor } from "../brands";
import { LEVEL_TONE, categoryLabel } from "../risk";

function Logo({ id, brand }: { id: string; brand: string }) {
  const [failed, setFailed] = useState(false);
  const src = logoFor(id);
  if (!src || failed) {
    return (
      <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-ink text-xs font-semibold text-faint">
        {brand.slice(0, 2).toUpperCase()}
      </div>
    );
  }
  return (
    <img
      src={src}
      alt=""
      width={36}
      height={36}
      loading="lazy"
      onError={() => setFailed(true)}
      className="h-9 w-9 shrink-0 rounded-lg bg-white/95 object-contain p-1"
    />
  );
}

export function ProductGrid({
  cards,
  persona,
  onSelect,
}: {
  cards: ProductCard[];
  persona: string;
  onSelect: (id: string) => void;
}) {
  // Which products changed answer when the buyer changed. Highlighting exactly
  // those is the difference between "the grid recoloured" and "switching to a
  // federal contractor just flagged seven things you were about to buy".
  const previous = useRef<Record<string, string>>({});
  const [changed, setChanged] = useState<Set<string>>(new Set());

  useEffect(() => {
    const now: Record<string, string> = {};
    for (const card of cards) now[card.id] = card.verdicts[persona]?.status;
    const before = previous.current;
    if (Object.keys(before).length) {
      const moved = new Set(
        cards.filter((c) => before[c.id] !== now[c.id]).map((c) => c.id),
      );
      setChanged(moved);
      const timer = setTimeout(() => setChanged(new Set()), 1600);
      previous.current = now;
      return () => clearTimeout(timer);
    }
    previous.current = now;
  }, [persona, cards]);

  const sorted = [...cards].sort((a, b) => {
    const d =
      ORDER[a.verdicts[persona].status] - ORDER[b.verdicts[persona].status];
    return d !== 0 ? d : a.brand.localeCompare(b.brand);
  });

  return (
    <section>
      <div className="mb-3 flex items-baseline gap-3">
        <h2 className="text-sm font-semibold tracking-wide text-fg">
          2 · What you are buying
        </h2>
        <span className="text-xs text-faint">
          Most constrained first. The chip is the legal verdict; the flag beneath
          it is Sayari&rsquo;s risk assessment, which is a separate question.
        </span>
      </div>

      {/* Exactly five across, so 25 products fill five rows with no orphan. */}
      <motion.ul
        layout
        className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5"
      >
        <AnimatePresence initial={false}>
          {sorted.map((card) => {
            const verdict = card.verdicts[persona];
            const style = STATUS[verdict.status];
            const justChanged = changed.has(card.id);

            return (
              <motion.li key={card.id} layout transition={{ duration: 0.28 }}>
                <button
                  onClick={() => onSelect(card.id)}
                  data-testid={`card-${card.id}`}
                  data-status={verdict.status}
                  className={[
                    "flex h-full w-full flex-col gap-2 rounded-xl border border-l-2 bg-surface/70 p-3 text-left",
                    "transition-colors hover:border-fg/25 hover:bg-raised",
                    style.edge,
                    justChanged ? "ring-2 ring-fg/35" : "",
                  ].join(" ")}
                >
                  <div className="flex items-center gap-2.5">
                    <Logo id={card.id} brand={card.brand} />
                    <div className="min-w-0">
                      <div className="truncate text-sm font-semibold text-fg">
                        {card.brand}
                      </div>
                      <div className="truncate text-xs text-faint">
                        {card.product}
                      </div>
                    </div>
                  </div>

                  <span
                    className={`inline-flex w-fit items-center gap-1.5 rounded-md border px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide ${style.chip}`}
                  >
                    <span className={`h-1.5 w-1.5 rounded-full ${style.dot}`} />
                    {style.short}
                  </span>

                  {verdict.status !== "no_restriction" && (
                    <p className="line-clamp-2 text-[11px] leading-snug text-muted">
                      {verdict.headline.replace(/^(Prohibited|Needs review): /, "")}
                    </p>
                  )}

                  {/* Sayari's risk assessment, shown even when nothing is
                      restricted. "No restriction" is a statement about law; these
                      flags are a different axis, and hiding them would imply a
                      clean bill of health the data does not support. */}
                  {card.flag_count > 0 && (
                    <p className="flex items-start gap-1 text-[11px] leading-snug text-faint">
                      <Flag
                        size={10}
                        className={`mt-0.5 shrink-0 ${
                          LEVEL_TONE[card.risk_level ?? ""] ?? "text-faint"
                        }`}
                      />
                      <span>
                        <span className={LEVEL_TONE[card.risk_level ?? ""]}>
                          {card.risk_level}
                        </span>{" "}
                        risk ·{" "}
                        {card.risk_categories.slice(0, 2).map(categoryLabel).join(", ")}
                      </span>
                    </p>
                  )}

                  <div className="mt-auto flex items-center justify-between pt-1 text-[10px] text-faint">
                    <span>
                      {card.family_size}{" "}
                      {card.family_size === 1 ? "entity" : "entities"}
                    </span>
                    {verdict.coverage_warning ? (
                      <span
                        className="flex items-center gap-1 text-check"
                        title={verdict.coverage_warning}
                      >
                        <AlertTriangle size={10} /> thin data
                      </span>
                    ) : (
                      card.family_flow > 0 && (
                        <span>
                          {card.family_flow >= 1000
                            ? `${Math.round(card.family_flow / 1000)}k`
                            : card.family_flow}{" "}
                          shipments
                        </span>
                      )
                    )}
                  </div>
                </button>
              </motion.li>
            );
          })}
        </AnimatePresence>
      </motion.ul>
    </section>
  );
}
