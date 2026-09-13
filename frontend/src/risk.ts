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
