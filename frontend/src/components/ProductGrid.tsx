import type { ProductCard, Status } from "../types";

const LABEL: Record<Status, string> = {
  prohibited: "Prohibited",
  review: "Diligence required",
  no_restriction: "No restriction identified",
};

export function ProductGrid({
  cards,
  persona,
  onSelect,
}: {
  cards: ProductCard[];
  persona: string;
  onSelect: (id: string) => void;
}) {
  // Most-constrained first so a change of persona is visible at a glance.
  const order: Record<Status, number> = {
    prohibited: 0,
    review: 1,
    no_restriction: 2,
  };
  const sorted = [...cards].sort((a, b) => {
    const d =
      order[a.verdicts[persona].status] - order[b.verdicts[persona].status];
    return d !== 0 ? d : a.brand.localeCompare(b.brand);
  });

  return (
    <ul className="grid">
      {sorted.map((card) => {
        const verdict = card.verdicts[persona];
        return (
          <li key={card.id}>
            <button
              className={`card ${verdict.status}`}
              onClick={() => onSelect(card.id)}
            >
              <span className="brand">{card.brand}</span>
              <span className="product">{card.product}</span>
              <span className={`chip ${verdict.status}`}>
                {LABEL[verdict.status]}
              </span>
              {verdict.status !== "no_restriction" && (
                <span className="why">{verdict.headline}</span>
              )}
              {verdict.coverage_warning && (
                <span className="gap" title={verdict.coverage_warning}>
                  ⚠ limited coverage
                </span>
              )}
              <span className="meta">
                {card.family_size} {card.family_size === 1 ? "entity" : "entities"}
                {card.family_flow > 0 &&
                  ` · ${card.family_flow.toLocaleString()} shipments`}
              </span>
            </button>
          </li>
        );
      })}
    </ul>
  );
}
