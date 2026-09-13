/** Sayari risk categories, rendered readably.
 *
 *  These are Sayari's own risk assessment and are deliberately NOT verdicts. A
 *  product can carry high-severity flags and still restrict nobody: "no
 *  restriction" is a statement about law, risk is a separate axis, and the UI
 *  must never let one read as the other.
 */
export const CATEGORY_LABELS: Record<string, string> = {
  forced_labor: "forced labour",
  export_controls: "export controls",
  regulatory_action: "regulatory action",
  political_exposure: "political exposure",
  adverse_media: "adverse media",
  sanctions: "sanctions",
  sanctions_and_export_control_lists: "sanctions lists",
  shell_company_risk: "shell company",
  environmental_risk: "environmental",
  relevant: "country context",
};

export const LEVEL_TONE: Record<string, string> = {
  critical: "text-stop",
  high: "text-check",
  elevated: "text-muted",
  relevant: "text-faint",
};

export function categoryLabel(slug: string): string {
  return CATEGORY_LABELS[slug] ?? slug.replace(/_/g, " ");
}

/** What being on each list actually does, and whether it is a sanction.
 *
 *  "On the list" is not self-explanatory: §1260H and §889 are procurement
 *  prohibitions, not sanctions, and nothing is blocked or frozen by either. Only
 *  OFAC SDN carries blocking sanctions. Saying so is the difference between a
 *  reader understanding the finding and assuming the worst one.
 */
export const LISTING_EFFECT: Record<
  string,
  { badge: string; effect: string; isSanction: boolean }
> = {
  section_1260h: {
    badge: "Bars DoD procurement",
    effect:
      "The Department of Defense may not procure from this entity. It is not a sanction: nothing is blocked or frozen, imports are unaffected, and anyone outside DoD procurement may buy freely.",
    isSanction: false,
  },
  section_889: {
    badge: "Bars federal contractors",
    effect:
      "Federal agencies and their contractors may not use this equipment, across the contractor's entire business rather than only its federal work. It is not a sanction and does not restrict anyone else.",
    isSanction: false,
  },
  fcc_covered: {
    badge: "Bars new FCC authorisation",
    effect:
      "New equipment from this entity cannot receive FCC authorisation, so it cannot lawfully be imported or marketed as new. Existing devices are unaffected and it is not a sanction.",
    isSanction: false,
  },
  ofac_sdn: {
    badge: "Blocking sanctions",
    effect:
      "Property is blocked and US persons are prohibited from dealing with this entity. This one is a sanction.",
    isSanction: true,
  },
};
