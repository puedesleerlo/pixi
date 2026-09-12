/** PIXIE v5 domain types — mirrors api/models.py and docs/SPEC-v5.md §3 (field names verbatim). */

export type Axes8 = number[]; // length 8, −3..3
export type Locale = "en" | "es";
export type Visibility = "private" | "unlisted" | "public";
export type DeckRole = "owner" | "curator" | "member";
export type EffectiveRole = "owner" | "curator" | "member" | "reader" | "guest";
export const ROLE_ORDER: Record<EffectiveRole, number> = { guest: 0, reader: 1, member: 2, curator: 3, owner: 4 };

export interface User {
  id: string;
  email?: string | null;
  name: string;
  avatar_url?: string | null;
  auth0_sub?: string | null;
  guest_token?: string | null;
  locale: Locale;
  is_guest?: boolean;
  is_admin?: boolean;
  created_at: string;
  upgraded_from_guest_at?: string | null;
}

export interface BaseDeck {
  id: string;
  slug: string;
  name: string;
  tradition: string;
  year: number | string;
  origin: string;
  rights_note: string;
  source_urls: string[];
  structure_template_id: string;
  card_count: number;
  status: "ready" | "partial" | "planned";
  symbol_registry_id?: string | null;
  attestation_sources: string[];
}

export interface BaseCard {
  id: string;
  base_deck_id: string;
  position_key: string;
  title: string;
  image_url: string;
  thumb_url: string;
  caption: string;
  attested_meaning_text?: string | null;
  attested_axes?: Axes8 | null;
}

export interface StructurePosition {
  key: string;
  title: string;
  group: string;
  order: number;
}
export interface StructureTemplate {
  id?: string;
  key: "tarot78" | "majors22" | "minors56" | "lenormand36" | "mantegna50" | "free" | string;
  name: string;
  positions: StructurePosition[];
}

export interface StyleReference {
  url: string;
  source: "base_card" | "upload" | "generated";
  weight: number;
}
export interface StyleGuide {
  prompt_prefix: string;
  negative_prompt?: string | null;
  palette: string[];
  line: "ink" | "woodcut" | "painted" | "flat" | "photo" | "custom";
  reference_images: StyleReference[];
  border: { style: string; color: string };
  aspect: "2.75x4.75" | "1x1.7" | "custom";
  style_centroid_embedding?: number[] | null;
}

export interface DeckSettings {
  who_can_create_cards: "members" | "curators";
  default_editor_policy: "any_member" | "curators" | "maker_list";
  allow_branches: boolean;
  allow_forks: boolean;
  allow_guest_readers: boolean;
  ready_threshold: number;
  max_edits_per_card: number;
  candidates_per_generation: number;
  fidelity_threshold: number;
  style_threshold: number;
  generation_quota_month: number;
  live_generation_in_sessions: boolean;
  provider?: string | null;
}

export interface DeckStats {
  cards: number;
  filled_positions: number;
  symbols: number;
  readings: number;
  sessions: number;
  forks: number;
  coherence_index: number | null;
  mean_fidelity: number | null;
  positions_total?: number;
  open_proposals?: number;
  needs_readings?: number;
}

export interface DeckOrigin {
  kind: "blank" | "base" | "fork";
  base_deck_id?: string | null;
  forked_from_deck_id?: string | null;
  forked_at_version_snapshot_id?: string | null;
}

export interface Deck {
  id: string;
  slug: string;
  name: string;
  description: string;
  cover_url?: string | null;
  owner_id: string;
  visibility: Visibility;
  structure_template_id: string;
  style_guide: StyleGuide;
  origin: DeckOrigin;
  settings: DeckSettings;
  stats: DeckStats;
  lineage: { ancestors: LineageRef[]; children: LineageRef[] };
  share_token?: string | null;
  /** Not in the spec: the caller's effective role, when the API includes it. */
  my_role?: EffectiveRole | null;
  structure?: StructureTemplate | null;
  created_at: string;
  updated_at?: string;
}
export interface LineageRef {
  deck_id: string;
  slug?: string;
  name?: string;
}

export interface Membership {
  id: string;
  deck_id: string;
  user_id: string;
  role: DeckRole;
  invited_by?: string | null;
  joined_at: string;
  user?: Pick<User, "id" | "name" | "email" | "avatar_url">;
}
export interface Invitation {
  id: string;
  deck_id: string;
  email?: string | null;
  link_token?: string | null;
  role: DeckRole;
  expires_at: string;
  accepted_at?: string | null;
}

export type SymbolPlacement = "any" | "center" | "top" | "bottom" | "left" | "right";
export type SymbolOrigin = "inherited_base" | "inherited_fork" | "community" | "upstream";
export type SymbolStatus = "active" | "proposed" | "merged" | "retired";
export type Coherence = "consistent" | "contested" | "untested";

export interface SymbolMeasured {
  coef: Axes8;
  ci_low: Axes8;
  ci_high: Axes8;
  n_cards: number;
  n_readings: number;
  n_edits: number;
  coherence: Coherence;
  declared_vs_measured: number | null;
}

export interface Symbol {
  id: string;
  deck_id: string;
  key: string;
  name: string;
  gloss: string;
  tags: string[];
  declared_axes: Axes8;
  declared_text: string;
  exemplar: { image_url: string | null; origin: "base_crop" | "generated" | "upload"; source_ref?: unknown } | null;
  placement: SymbolPlacement;
  origin: SymbolOrigin;
  inherited_from?: { base_deck_id?: string; deck_id?: string; symbol_id: string } | null;
  attestations: { source: string; note: string }[];
  prior_axes?: Axes8 | null;
  prior_source?: "attestation" | "parent_grammar" | null;
  status: SymbolStatus;
  merged_into_symbol_id?: string | null;
  proposed_by?: string | null;
  approved_by?: string | null;
  approved_at?: string | null;
  measured: SymbolMeasured;
  cards_using?: number;
}

export interface SymbolProposal {
  id: string;
  deck_id: string;
  symbol_draft: Partial<Symbol> & { name: string; gloss: string; declared_axes: Axes8 };
  note: string;
  status: "open" | "approved" | "declined";
  proposed_by?: string;
  decided_by?: string | null;
  decision_note?: string | null;
  created_at: string;
}

export type CardStatus = "draft" | "reading" | "open" | "landed" | "closed" | "archived";

export interface EditRequest {
  id?: string;
  user_id: string;
  note: string;
  status: "open" | "approved" | "declined";
  user_name?: string;
}

export interface Card {
  id: string;
  deck_id: string;
  position_key: string;
  title?: string | null;
  maker_id: string;
  maker_name?: string;
  intent?: { statement: string; axes: Axes8 } | null; // encoders only
  approved_editors: "*" | string[];
  edit_requests: EditRequest[];
  status: CardStatus;
  current_version_id: string | null;
  branches: { branch_key: string; head_version_id: string }[];
  tags: string[];
  share_token?: string | null;
  current_version?: Version | null;
  verdict?: Verdict | null;
  fidelity?: number | null;
  n_readings?: number;
  editors_count?: number;
  contested?: boolean;
  off_style?: boolean;
  created_at: string;
}

export interface Region {
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface Generation {
  mode: "prompt" | "reference" | "reinterpret" | "upload" | "variation";
  reference_image_url?: string | null;
  prompt_user: string;
  prompt_full: string;
  provider: string;
  model: string;
  seed?: number | null;
  candidates: { image_url: string; style_score: number }[];
  chosen_index: number | null;
}

export type EditOp = "add" | "remove" | "replace" | "emphasize" | "deemphasize" | "reposition" | "cosmetic";

export interface Edit {
  op: EditOp;
  symbol_id?: string | null;
  to_symbol_id?: string | null;
  region?: Region | null;
  prompt_user?: string | null;
  prompt_full: string;
  provider: string;
  model: string;
  seed?: number | null;
  candidates: { image_url: string; fidelity: number; containment: number; style_score: number; heatmap_url?: string }[];
  chosen_index: number | null;
  bet_axis?: number | null;
  rationale: string;
  editor_id: string;
  editor_name?: string;
  counts_as_experiment: boolean;
}

export interface Version {
  id: string;
  card_id: string;
  deck_id: string;
  v: number;
  branch_key: string;
  base_version_id?: string | null;
  image_url: string;
  thumb_url: string;
  width: number;
  height: number;
  symbols_declared: { symbol_id: string; placement?: SymbolPlacement | null }[];
  symbols_detected: { symbol_id: string; salience: number; bbox?: Region | null; tagged_by: "vision" | "human" | "declared_only" }[];
  how: (Generation & { kind?: "generation" }) | (Edit & { kind?: "edit" });
  checks: { fidelity?: number | null; containment?: number | null; style_score: number | null; symbols_missing: string[]; safety: "ok" | "blocked" };
  created_by: string;
  created_at: string;
  n_readings?: number;
}

export interface Reading {
  id: string;
  deck_id: string;
  card_id: string;
  version_id: string;
  reader_id: string;
  session_id?: string | null;
  round_id?: string | null;
  free_text?: string | null;
  axes: Axes8;
  latency_ms: number;
  synthetic: boolean;
  created_at: string;
}

export interface Verdict {
  version_id: string;
  n: number;
  V?: number;
  S?: number;
  S_null95?: number;
  k?: number;
  verdict: "legible" | "polysemous" | "noisy" | "collecting";
  clusters?: { label: string; label_by?: string; centroid: Axes8; n: number }[];
  needed?: number;
}

export interface Grammar {
  deck_id: string;
  axes?: [string, string][];
  n_readings: number;
  n_real?: number;
  n_synthetic?: number;
  n_edits?: number;
  symbols: GrammarRow[];
  computed_at?: string;
}
export interface GrammarRow {
  symbol_id: string;
  name?: string;
  coef: Axes8;
  ci_low: Axes8;
  ci_high: Axes8;
  n_readings: number;
  n_edits: number;
  prior_axes?: Axes8 | null;
  drift_from_prior?: number | null;
  mean_effect?: Axes8 | null;
  coherence?: Coherence;
}

export interface Session {
  id: string;
  deck_id: string;
  code: string;
  host_id: string;
  mode: "reading" | "relay";
  settings: { read_timer: number; edit_timer: number; generation_timer: number; live_generation: boolean; guests_allowed: boolean; max_edits: number };
  players: { user_or_guest_id: string; nickname: string; role: "host" | "player" | "reader"; connected: boolean }[];
  state: "lobby" | "compose" | "read" | "reveal" | "edit" | "generating" | "summary" | "ended";
  round_ends_at?: string | null;
  current_card_id?: string | null;
  current_version_id?: string | null;
  turn_order: string[];
  turn_index: number;
  created_at: string;
}
export interface Round {
  id: string;
  session_id: string;
  kind: "read" | "edit";
  card_id: string;
  version_id: string;
  maker_or_editor_id: string;
  started_at: string;
  ended_at?: string | null;
  scores: { user_id: string; points: number; reason: string }[];
}

export interface ForkSnapshot {
  id: string;
  source_deck_id: string;
  target_deck_id: string;
  taken_at: string;
  copied: { symbols: number; cards: number; style: boolean; structure: boolean };
}
export interface UpstreamProposal {
  id: string;
  from_deck_id: string;
  to_deck_id: string;
  kind: "version" | "symbol";
  version_id?: string | null;
  symbol_id?: string | null;
  note: string;
  status: "open" | "accepted" | "declined";
  decided_by?: string | null;
  decision_note?: string | null;
  result_ref?: string | null;
  created_at: string;
}

export interface Job {
  id: string;
  kind: "generate" | "edit" | "tag" | "fidelity" | "grammar" | "reinterpret_batch" | "ingest_base" | "export" | string;
  deck_id?: string | null;
  payload?: unknown;
  status: "queued" | "running" | "done" | "failed";
  progress: number;
  note?: string | null;
  result?: unknown;
  error?: string | null;
  attempts: number;
  created_by: string;
  created_at: string;
}
export interface Notification {
  id: string;
  user_id: string;
  kind: string;
  deck_id?: string | null;
  card_id?: string | null;
  text: string;
  read_at?: string | null;
  created_at: string;
}
export interface Activity {
  id: string;
  deck_id: string;
  actor_id: string;
  actor_name?: string;
  kind: string;
  refs: Record<string, string>;
  created_at: string;
}

/** Wizard payload for POST /api/decks (contract §1 + spec §5.2). */
export interface DeckWizardPayload {
  name: string;
  description?: string;
  visibility: Visibility;
  origin: { kind: "blank" | "base" | "fork"; base_deck_id?: string; forked_from_deck_id?: string };
  structure_template_id: string;
  style_guide?: Partial<StyleGuide>;
  style_from_base_deck_id?: string;
  import_symbols: string[];
  card_mode: "inherit" | "reference";
  invites: { email: string; role: DeckRole }[];
}

export interface Coherence7 {
  coherence_index: number | null;
  style: { mean: number | null; spread: number | null; outliers: { card_id: string; position_key?: string; style_score: number }[] };
  semantic: { consistent: number; contested: number; untested: number; contested_symbols: { symbol_id: string; name?: string; cards: { card_id: string; angle: number }[] }[] };
  structural: { filled: number; total: number; duplicates: string[]; drafts_without_intent: number; closed_without_landing: number };
  transmission: { mean_fidelity: number | null; verdicts: Record<string, number>; needs_readings: number; bandwidth: { n_symbols: number; mean_fidelity: number; n_cards: number }[] };
}
