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
  risk_level: string | null;
  risk_categories: string[];
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

export interface SanctionListing {
  type: string | null;
  list: string | null;
  program: string | null;
  from_date: string | null;
  to_date: string | null;
}

export interface ShipmentExample {
  arrival_date: string | null;
  departure_date: string | null;
  supplier: string[];
  descriptions: string[];
  hs_codes: string[];
}

/** A sanctioned party reached through a trade edge, with the shipments dated
 *  against that party's designation date. */
export interface SanctionedTrade {
  id: string;
  label: string;
  countries: string[];
  edge: string | null;
  hops: number;
  via_factor: string;
  listings: SanctionListing[];
  designated_on: string | null;
  shipment_total: number;
  examined: number;
  complete: boolean;
  latest_shipment: string | null;
  count_after: number;
  count_before: number;
  count_undatable: number;
  after_designation: ShipmentExample[];
  before_designation: ShipmentExample[];
  assessment: string;
  ofac_sdn_confirmed: boolean;
  ofac_sdn: { sdn_name: string; program: string | null; type: string | null } | null;
  corroboration: string;
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
  sanctioned_trade: SanctionedTrade[];
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
  api: {
    /** Calls actually spent building this snapshot, summed across stages. */
    snapshot_cost: {
      total: number;
      by_stage: Record<string, number>;
      complete: boolean;
    };
    /** Whole-account metering over 30 days. Includes development, so it is much
     *  larger than the snapshot cost and must never be presented as it. */
    account_usage_last_30d?: Record<string, number>;
  };
}
