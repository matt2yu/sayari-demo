import { motion } from "framer-motion";
import type { Persona, ProductCard, Status } from "../types";
import { STATUS } from "../status";

const SPLIT: Status[] = ["prohibited", "review", "no_restriction"];

/** The answer, in a sentence, before any card is read.
 *
 *  The bar animates between personas on purpose: a number quietly changing from
 *  0 to 7 is easy to miss, a bar visibly filling is not. That movement is the
 *  single clearest expression of "legal depends on who is asking".
 */
export function ImpactBar({
  cards,
  persona,
  personas,
}: {
  cards: ProductCard[];
  persona: string;
  personas: Persona[];
}) {
  const counts = SPLIT.reduce(
    (acc, s) => {
      acc[s] = cards.filter((c) => c.verdicts[persona]?.status === s).length;
      return acc;
    },
    {} as Record<Status, number>,
  );
  const label = personas.find((p) => p.key === persona)?.label ?? "";
  const flagged = counts.prohibited + counts.review;
  const article = /^[AEIOU]/.test(label) ? "an" : "a";

  return (
    <section className="mb-8 rounded-xl border border-line bg-surface/60 p-5">
      <p className="text-lg leading-snug text-fg">
        As {article} <span className="font-semibold">{label}</span>,{" "}
        {flagged === 0 ? (
          <>
            <span className="font-semibold text-clear">none</span> of these 25
            products carries a restriction we can identify.
          </>
        ) : (
          <>
            {counts.prohibited > 0 && (
              <>
                <span className="font-semibold text-stop">
                  {counts.prohibited}
                </span>{" "}
                {counts.prohibited === 1 ? "product is" : "products are"}{" "}
                <span className="text-stop">prohibited</span>
                {counts.review > 0 && " and "}
              </>
            )}
            {counts.review > 0 && (
              <>
                <span className="font-semibold text-check">{counts.review}</span>{" "}
                {counts.review === 1 ? "needs" : "need"}{" "}
                <span className="text-check">diligence</span>
              </>
            )}{" "}
            before purchase.
          </>
        )}
      </p>

      <div className="mt-4 flex h-2 overflow-hidden rounded-full bg-ink">
        {SPLIT.map((status) =>
          counts[status] > 0 ? (
            <motion.div
              key={status}
              layout
              className={STATUS[status].bar}
              initial={false}
              animate={{ flexGrow: counts[status] }}
              transition={{ type: "spring", stiffness: 220, damping: 28 }}
            />
          ) : null,
        )}
      </div>

      {flagged === 0 && (
        <p className="mt-3 text-sm text-muted">
          Same products, same data.{" "}
          <span className="text-fg">Switch to Federal Contractor</span> and seven
          of them become a problem — because Section 889 binds contractors, not
          households.
        </p>
      )}

      <div className="mt-2.5 flex flex-wrap gap-x-5 gap-y-1 text-xs text-faint">
        {SPLIT.map((status) => (
          <span key={status} className="flex items-center gap-1.5">
            <span
              className={`inline-block h-2 w-2 rounded-full ${STATUS[status].dot}`}
            />
            {counts[status]} {STATUS[status].label.toLowerCase()}
          </span>
        ))}
      </div>
    </section>
  );
}
