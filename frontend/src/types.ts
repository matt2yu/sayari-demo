export type Status = "prohibited" | "review" | "no_restriction";

export interface Persona {
  key: string;
  label: string;
  blurb: string;
  regimes: string[];
}

export interface Reason {
  authority: string;
  citation: string;
  binds: string;
  severity: Status;
  detail: string;
}

export interface Verdict {
  status: Status;
  headline: string;
  reasons: Reason[];
  coverage_warning: string | null;
}

export interface ProductCard {
  id: string;
  brand: string;
  product: string;
  category: string;
  country: string;
  parent: string | null;
  resolved: boolean;
  family_size: number;
  family_flow: number;
  flag_count: number;
  seed_flag_count: number;
  worst_status: Status;
  verdicts: Record<string, Verdict>;
}

export interface Hop {
  hop: number;
  edge: string | null;
  id: string;
  label: string;
  countries: string[];
  sanctioned: boolean;
  seed_risks: string[];
}

export interface Chain {
  kind: "ownership" | "trade" | "mixed";
  hops: Hop[];
  raw: string;
}

export interface Flag {
  id: string;
  label: string | null;
  description: string | null;
  level: string | null;
  /** seed = on the entity itself. network = derived by traversing the graph. */
  risk_type: string;
  categories: string[];
  carried_by: string[];
  chains?: Chain[];
  sources: string[];
}

export interface FamilyMember {
  id: string;
  via: string;
  label: string;
  translated_label: string | null;
  countries: string[];
  degree: number;
  sent: number;
  received: number;
  sanctioned: boolean;
  duplicate_ids: string[];
}

export interface Rejected {
  id: string;
  label: string;
  rejected_because: string;
}

export interface RegimeHit {
  regime: string;
  authority: string;
  binds: string;
  citation: string;
  how: "direct" | "owner" | "seed_risk";
  owner?: string;
  entity?: string;
  matched?: string;
  hops?: number;
  edge?: string;
  factor?: string;
}

export interface ProductDetail extends ProductCard {
  legal_name: string;
  notes: string | null;
  family: FamilyMember[];
  rejected: Rejected[];
  flags: Flag[];
  context_flags: Flag[];
  dropped_flags: (Flag & { dropped_because: string })[];
  regime_hits: RegimeHit[];
  caveats: string[];
}

export interface Regime {
  key: string;
  authority: string;
  citation: string;
  binds: string;
  scope: string;
}

export interface Meta {
  generated_at: string;
  source: string;
  product_count: number;
  personas: Persona[];
  regimes: Regime[];
  caveats: string[];
  api: { total_calls: number; by_endpoint: Record<string, number> };
}
