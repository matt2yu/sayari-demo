import { Building2, Home, Landmark, Shield } from "lucide-react";
import type { Persona, ProductCard, Status } from "../types";
import { STATUS } from "../status";

const ICONS: Record<string, typeof Home> = {
  consumer: Home,
  enterprise: Building2,
  federal_contractor: Landmark,
  dod: Shield,
};

/** The one number worth leading with, and what to call it.
 *
 *  A profile with 1 prohibited product has 1 problem, not 1 problem plus 1
 *  "needing attention". Naming the worst status directly is both shorter and
 *  more accurate than a combined total.
 */
function leadWith(counts: Record<Status, number>, total: number) {
  if (counts.prohibited > 0)
    return {
      status: "prohibited" as Status,
      count: counts.prohibited,
      wording: counts.prohibited === 1 ? "is prohibited" : "are prohibited",
      style: STATUS.prohibited,
    };
  if (counts.review > 0)
    return {
      status: "review" as Status,
      count: counts.review,
      wording: counts.review === 1 ? "needs review" : "need review",
      style: STATUS.review,
    };
  return {
    status: "no_restriction" as Status,
    count: total,
    wording: "have no restrictions",
    style: STATUS.no_restriction,
  };
}

function tally(cards: ProductCard[], key: string) {
  const out: Record<Status, number> = {
    prohibited: 0,
    review: 0,
    no_restriction: 0,
  };
  for (const card of cards) out[card.verdicts[key]?.status ?? "no_restriction"]++;
  return out;
}

/** Step one of the page, and the whole argument.
 *
 *  Each option shows its own flagged count *before* you pick it. Seeing
 *  "0 flagged" next to Consumer and "7 flagged" next to DoD Supplier is what
 *  makes the point land -- otherwise the page is 25 tiles that change colour for
 *  no visible reason.
 */
export function PersonaPicker({
  personas,
  cards,
  active,
  onChange,
}: {
  personas: Persona[];
  cards: ProductCard[];
  active: string;
  onChange: (key: string) => void;
}) {
  return (
    <section className="mb-8">
      <div className="mb-3 flex items-baseline gap-3">
        <h2 className="text-sm font-semibold tracking-wide text-fg">
          1 · Who is buying?
        </h2>
        <span className="text-xs text-faint">
          The same 25 products, four different legal answers.
        </span>
      </div>

      <div className="grid items-stretch gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {personas.map((persona) => {
          const Icon = ICONS[persona.key] ?? Home;
          const counts = tally(cards, persona.key);
          const headline = leadWith(counts, cards.length);
          const on = persona.key === active;

          return (
            <button
              key={persona.key}
              onClick={() => onChange(persona.key)}
              aria-pressed={on}
              className={[
                "group flex h-full flex-col rounded-xl border p-4 text-left transition-all",
                on
                  ? "border-fg/40 bg-raised shadow-lg shadow-black/40 ring-1 ring-fg/15"
                  : "border-line bg-surface/40 hover:border-fg/20 hover:bg-surface",
              ].join(" ")}
            >
              <div className="flex items-center gap-2">
                <Icon
                  size={16}
                  className={on ? "text-fg" : "text-faint group-hover:text-muted"}
                />
                <span
                  className={[
                    "text-sm font-semibold",
                    on ? "text-fg" : "text-muted",
                  ].join(" ")}
                >
                  {persona.label}
                </span>
              </div>

              <p className="mt-2 text-xs leading-relaxed text-faint">
                {persona.blurb}
              </p>

              {/* Lead with the most severe count and name that status. Showing a
                  combined "needs attention" total alongside a prohibited count
                  counted the same product twice: 1 needing attention *was* the 1
                  prohibited. */}
              <div className="mt-auto border-t border-line pt-4">
                <div className="flex items-baseline gap-1.5">
                  <span
                    className={`text-2xl font-semibold tabular-nums ${headline.style.text}`}
                  >
                    {headline.count}
                  </span>
                  <span className="text-xs text-faint">
                    of {cards.length} {headline.wording}
                  </span>
                </div>
                <div className="mt-1 flex h-4 items-center gap-1.5 text-[11px] text-check">
                  {headline.status === "prohibited" && counts.review > 0 && (
                    <>
                      <span className="h-1.5 w-1.5 rounded-full bg-check" />
                      {counts.review} more need review
                    </>
                  )}
                </div>
              </div>
            </button>
          );
        })}
      </div>
    </section>
  );
}
