// Typed client for the PIXIE API — contract v4 (docs/CONTRACT.md §5–§9).

const CONFIGURED_API_URL = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") || "http://localhost:8000";

/**
 * Where the API lives. If the configured URL points at localhost but this page was opened from
 * another host (a phone on the LAN, a tunnel), the API is assumed to sit on that same host: a phone
 * can never reach the laptop's "localhost".
 */
export function apiUrl(): string {
  if (typeof window === "undefined") return CONFIGURED_API_URL;
  try {
    const u = new URL(CONFIGURED_API_URL);
    const here = window.location.hostname;
    if ((u.hostname === "localhost" || u.hostname === "127.0.0.1") && here && here !== "localhost" && here !== "127.0.0.1") {
      u.hostname = here;
      return u.toString().replace(/\/$/, "");
    }
  } catch {
    /* fall through */
  }
  return CONFIGURED_API_URL;
}

export const API_URL = CONFIGURED_API_URL;

export type Axes = number[]; // length 8, −3..3
export type Slot = "center" | "top" | "bottom" | "left" | "right";
export type SizeClass = "large" | "small";
export type Origin = "cut" | "generated" | "tile";

// ---------------------------------------------------------------- libraries / elements

export interface Library {
  id: string;
  name: string;
  kind: "base" | "community";
  source_deck?: string | null;
  source_year?: number | null;
  rights_note?: string | null;
  deck_id?: string | null;
}

export interface Attestation {
  card_id?: string;
  source: string;
  note: string;
}

export interface Element {
  id: string;
  library_id: string;
  label: string;
  gloss?: string;
  parent_id: string | null;
  size_class?: SizeClass | null; // groups have none and are never placeable
  origin?: Origin;
  image_url: string | null; // null → text tile
  caption?: string;
  source_card?: string | null;
  historical_prior?: Axes | null;
  prior_coded_by?: string | null;
  attestations?: Attestation[];
}

/** What a version carries per slot, as the API returns it inside rooms, reveals and chains. */
export interface PlacedElement {
  element_id: string;
  slot: Slot;
  label: string;
  image_url: string | null;
  origin?: Origin;
  size_class?: SizeClass | null;
  caption?: string;
}

export interface LibraryGroup {
  id: string;
  name: string;
  elements: Element[];
}

// ---------------------------------------------------------------- decks

export interface Member {
  guest_id: string;
  nickname: string;
  joined_at?: string;
}

export interface Deck {
  id: string;
  name: string;
  code: string;
  owner_id?: string;
  libraries: string[];
  members: Member[];
  open_read?: boolean;
  max_edits?: number;
  ready_threshold?: number;
  created_at?: string;
  community_library_id?: string;
  n_members?: number;
  n_cards?: number;
}

export type CardStatus = "reading" | "open" | "landed" | "closed";

export interface EditMove {
  type: "add" | "remove" | "swap" | "move";
  element_id: string;
  element_label?: string;
  to_element_id?: string | null;
  to_element_label?: string | null;
  to_slot?: Slot | null;
  editor_id?: string;
  editor_nickname?: string;
  bet_axis: number;
  rationale?: string | null;
}

export interface EditEffect {
  bet_axis: number;
  delta: number | null;
  gap_before: number | null;
  hit: boolean;
  n_pairs: number;
  shift: Axes | null;
  points?: number;
}

export interface Landing {
  landed: boolean;
  threshold: number;
  points_each: number;
  encoders: string[];
}

export interface ChainVersion {
  v: number;
  version_id: string;
  elements: PlacedElement[];
  edit: EditMove | null;
  n_readings: number;
  n_real: number;
  fidelity: number | null;
  delta_fidelity?: number | null;
  edit_effect?: EditEffect | null;
  points?: Record<string, number> | null;
}

export interface ChainCard {
  id: string;
  deck_id?: string;
  mode?: "room" | "deck";
  status: CardStatus;
  title?: string | null;
  title_by?: string | null;
  maker_nickname?: string | null;
  maker_id?: string;
  landed: boolean;
  statement: string | null;
  created_at?: string;
  finished_at?: string | null;
  max_edits?: number;
  synthetic?: boolean;
  approved_editors?: "*" | string[];
  latest_version_id?: string;
}

export interface Chain {
  card: ChainCard;
  versions: ChainVersion[];
  landing?: Landing | null;
}

export interface DeckHome {
  deck: Deck;
  cards: Record<CardStatus, Chain[]>;
}

// ---------------------------------------------------------------- rooms

export interface Player {
  guest_id: string;
  nickname: string;
  joined_at: string;
}

export type Phase = "lobby" | "compose" | "read" | "reveal" | "edit" | "ended";
export type Role = "host" | "player" | "maker" | "editor" | "reader" | "spectator";

export interface RoundVersion {
  v: number;
  elements: PlacedElement[];
}

export interface Round {
  card_id: string | null;
  version_id: string | null;
  v: number;
  maker_id: string;
  holder_id: string;
  editor_id?: string | null;
  phase_ends_at: string | null;
  submitted_reader_ids: string[];
  reader_ids?: string[];
  n_card: number;
  n_readers?: number;
  n_submitted?: number;
  version: RoundVersion | null;
  max_edits: number;
  replay?: boolean;
  maker_nickname?: string;
  editor_nickname?: string;
  holder_nickname?: string;
}

export interface HistoryItem {
  card_id: string;
  n_card?: number;
  maker_id?: string;
  maker_nickname?: string;
  status?: CardStatus | "skipped";
  landed?: boolean;
  v?: number;
  points?: Record<string, number> | number | null;
  note?: string;
  replay?: boolean;
}

export interface IntentView {
  statement: string;
  axes: Axes;
  gaps_signed?: Axes | null;
}

export interface Room {
  code: string;
  deck_id: string;
  deck_code?: string;
  host_id: string;
  players: Player[];
  turn_order: string[];
  maker_index: number;
  makers_done: string[];
  scores: Record<string, number>;
  phase: Phase;
  round: Round | null;
  history: HistoryItem[];
  created_at: string;
  server_time: string;
  small_room?: boolean;
  you: {
    guest_id: string | null;
    role: Role;
    is_host: boolean;
    submitted: boolean;
    previous_axes: Axes | null;
  };
  intent?: IntentView | null;
  reveal?: Reveal | null;
  reveal_error?: string;
}

// ---------------------------------------------------------------- reveal

export interface RevealReading {
  reader_id: string;
  nickname: string;
  axes: Axes;
  free_text: string | null;
  d_axes: number;
  d_embed: number | null;
  d_total: number;
  inside_radius: boolean;
  xy: [number, number];
  prev_xy?: [number, number] | null;
  prev_axes?: Axes | null;
  shift?: Axes | null;
  synthetic: boolean;
}

export interface Cluster {
  centroid: Axes;
  n: number;
  member_idx: number[];
  label?: string;
  label_by?: "k2" | "template";
}

export interface Verdict {
  verdict: "collecting" | "legible" | "polysemous" | "noisy";
  n: number;
  needed?: number;
  V?: number;
  S?: number;
  S_null95?: number;
  k?: number;
  P?: number;
  noise?: number;
  labels?: number[];
  clusters?: Cluster[];
}

export interface GrammarStripItem {
  element_id: string;
  label: string;
  slot?: Slot;
  salience: number;
  coef: Axes;
  ci_low: Axes;
  ci_high: Axes;
  n: number;
  n_edits?: number;
  historical_support: number | null;
  origin?: Origin;
}

export interface MakerScore {
  points: number | null;
  f: number | null;
  n: number;
  needs: number;
}

export interface GapAbs {
  axis: number;
  abs: number;
}

export interface Reveal {
  card: {
    id: string;
    status: CardStatus;
    title?: string | null;
    title_by?: string | null;
    maker_nickname: string;
    v: number;
    max_edits: number;
    landed: boolean;
    statement: string | null;
  };
  version: { v: number; elements: PlacedElement[]; edit: EditMove | null };
  intent_xy: [number, number];
  radius: number;
  pca_note: string;
  readings: RevealReading[];
  fidelity: number | null;
  fidelity_prev: number | null;
  delta_fidelity: number | null;
  gaps_abs: GapAbs[];
  gaps_signed: Axes | null;
  maker_score: MakerScore | null;
  edit_effect: EditEffect | null;
  landing: Landing | null;
  verdict: Verdict;
  grammar_strip: GrammarStripItem[];
  grammar_strip_before: GrammarStripItem[];
  edited_element_id: string | null;
  you: { d_total: number | null; shift: Axes | null };
  replay?: boolean;
}

// ---------------------------------------------------------------- grammar

export interface GrammarElement {
  element_id: string;
  library_id?: string;
  label: string;
  parent_id: string | null;
  origin?: Origin;
  coef: Axes;
  ci_low: Axes;
  ci_high: Axes;
  n: number;
  n_edits?: number;
  mean_effect?: Axes | null;
  historical_prior: Axes | null;
  historical_support: number | null;
  attestations?: Attestation[];
}

export interface Grammar {
  axes: [string, string][];
  n_readings: number;
  n_real: number;
  n_synthetic: number;
  n_edits?: number;
  elements: GrammarElement[];
}

export interface BandwidthPoint {
  n_elements: number;
  mean_fidelity: number;
  n_cards: number;
}

export interface Config {
  w_axes: number;
  w_embed: number;
  radius: number;
  v_lo: number;
  alpha: number;
}

export interface Health {
  ok: boolean;
  store: "memory" | "mongo";
  embed_backend: string;
  naming_backend: string;
  n_libraries?: number;
  n_elements?: number;
  n_decks?: number;
  n_cards?: number;
  n_readings: number;
  n_real: number;
  n_synthetic: number;
}

/** What the deck read queue hands a reader (T2). */
export interface ReadTask {
  card_id: string;
  version_id: string;
  v: number;
  version: RoundVersion;
  n_readings?: number;
  previous_axes?: Axes | null;
}

// ---------------------------------------------------------------- guest id

const GUEST_KEY = "pixie_guest";

export function getGuestId(): string | null {
  if (typeof window === "undefined") return null;
  try {
    const ls = window.localStorage.getItem(GUEST_KEY);
    if (ls) return ls;
  } catch {}
  const m = document.cookie.match(/(?:^|; )pixie_guest=([^;]+)/);
  return m ? decodeURIComponent(m[1]) : null;
}

export function setGuestId(id: string) {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(GUEST_KEY, id);
  } catch {}
  document.cookie = `pixie_guest=${encodeURIComponent(id)}; path=/; max-age=31536000; SameSite=Lax`;
}

const NICK_KEY = "pixie_nick";
export function getNickname(): string {
  if (typeof window === "undefined") return "";
  try {
    return window.localStorage.getItem(NICK_KEY) || "";
  } catch {
    return "";
  }
}
export function setNickname(n: string) {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(NICK_KEY, n);
  } catch {}
}

// ---------------------------------------------------------------- fetch

export class ApiError extends Error {
  status: number;
  constructor(status: number, detail: string) {
    super(detail);
    this.status = status;
  }
}

/** Optional bearer token (set after a magic-link login when cookies are blocked). */
export function getToken(): string | null {
  try {
    return localStorage.getItem("pixie_token");
  } catch {
    return null;
  }
}
export function setToken(t: string | null) {
  try {
    if (t) localStorage.setItem("pixie_token", t);
    else localStorage.removeItem("pixie_token");
  } catch {}
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const token = getToken();
  const res = await fetch(`${apiUrl()}${path}`, {
    ...init,
    credentials: "include",
    headers: {
      ...(init?.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(init?.headers || {}),
    },
    cache: "no-store",
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const j = await res.json();
      detail = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail ?? j);
    } catch {}
    throw new ApiError(res.status, detail);
  }
  return (await res.json()) as T;
}

const get = <T,>(path: string) => request<T>(path);
const post = <T,>(path: string, body: unknown) =>
  request<T>(path, { method: "POST", body: JSON.stringify(body) });

const q = (s: string | null | undefined) => encodeURIComponent(s ?? "");

// ---------------------------------------------------------------- normalisers
// The server may return a few payloads in either of two shapes; accept both.

type ElementsResponse =
  | Element[]
  | LibraryGroup[]
  | { libraries: LibraryGroup[] }
  | { elements: Element[]; libraries?: Library[] };

export function normaliseElements(res: ElementsResponse, libs?: Library[]): LibraryGroup[] {
  const libName = new Map<string, string>((libs ?? []).map((l) => [l.id, l.name]));
  let groups: LibraryGroup[] | null = null;
  let flat: Element[] | null = null;
  if (Array.isArray(res)) {
    if (res.length && "elements" in res[0]) groups = res as LibraryGroup[];
    else flat = res as Element[];
  } else if ("libraries" in res && Array.isArray(res.libraries) && !("elements" in res)) {
    groups = res.libraries;
  } else if ("elements" in res) {
    flat = res.elements;
    for (const l of (res as { libraries?: Library[] }).libraries ?? []) libName.set(l.id, l.name);
  }
  if (groups) return groups.map((g) => ({ ...g, elements: g.elements.filter(isPlaceable) }));
  const by = new Map<string, LibraryGroup>();
  for (const e of flat ?? []) {
    if (!isPlaceable(e)) continue;
    const id = e.library_id ?? "unknown";
    if (!by.has(id)) by.set(id, { id, name: libName.get(id) ?? prettyLib(id), elements: [] });
    by.get(id)!.elements.push(e);
  }
  return [...by.values()];
}

export function isPlaceable(e: Element): boolean {
  return !!e.size_class;
}

function prettyLib(id: string) {
  if (id === "smith1909") return "Smith 1909";
  if (id === "conver1760") return "Conver 1760";
  return id;
}

type DeckHomeResponse = DeckHome | (Deck & { cards: Chain[] | Record<string, Chain[]> });

export function normaliseDeckHome(res: DeckHomeResponse): DeckHome {
  const deck: Deck = "deck" in res && res.deck ? (res.deck as Deck) : (res as Deck);
  const raw = (res as { cards?: Chain[] | Record<string, Chain[]> }).cards ?? {};
  const cards: Record<CardStatus, Chain[]> = { reading: [], open: [], landed: [], closed: [] };
  if (Array.isArray(raw)) {
    for (const ch of raw) {
      const s = (ch.card?.status ?? "closed") as CardStatus;
      (cards[s] ?? cards.closed).push(ch);
    }
  } else {
    for (const k of Object.keys(raw)) {
      const s = k as CardStatus;
      if (cards[s]) cards[s] = raw[k] ?? [];
    }
  }
  return { deck, cards };
}

// ---------------------------------------------------------------- endpoints

export interface JoinResponse {
  guest_id: string;
  room: Room;
}

export interface ComposeBody {
  guest_id: string;
  statement: string;
  axes: Axes;
  elements: { element_id: string; slot: Slot }[];
}

export interface EditBody {
  guest_id: string;
  type: EditMove["type"];
  element_id: string;
  to_element_id?: string;
  to_slot?: Slot;
  bet_axis: number;
  rationale?: string;
}

export interface ReadingBody {
  guest_id: string;
  axes: Axes;
  free_text?: string;
  latency_ms?: number;
}

export const api = {
  health: () => get<Health>("/api/health"),

  // rooms
  createRoom: (nickname: string, guest_id: string | null, deck_code?: string) =>
    post<JoinResponse>("/api/rooms", { nickname, guest_id: guest_id ?? undefined, deck_code }),
  joinRoom: (code: string, nickname: string, guest_id: string | null) =>
    post<JoinResponse>(`/api/rooms/${code}/join`, { nickname, guest_id: guest_id ?? undefined }),
  getRoom: (code: string, guest_id: string | null) => get<Room>(`/api/rooms/${code}?guest_id=${q(guest_id)}`),
  startRoom: (code: string, guest_id: string) => post<Room>(`/api/rooms/${code}/start`, { guest_id }),
  compose: (code: string, body: ComposeBody) => post<Room>(`/api/rooms/${code}/compose`, body),
  postReading: (code: string, body: ReadingBody) => post<Room>(`/api/rooms/${code}/reading`, body),
  edit: (code: string, body: EditBody) => post<Room>(`/api/rooms/${code}/edit`, body),
  continueRoom: (code: string, guest_id: string) => post<Room>(`/api/rooms/${code}/continue`, { guest_id }),
  replay: (code: string, guest_id: string) => post<Room>(`/api/rooms/${code}/replay`, { guest_id }),

  // libraries / decks
  libraries: () => get<Library[]>("/api/libraries"),
  libraryElements: (id: string) => get<ElementsResponse>(`/api/libraries/${id}/elements`),
  decks: () => get<Deck[]>("/api/decks"),
  createDeck: (body: { name: string; libraries: string[]; guest_id: string | null; nickname: string }) =>
    post<Deck>("/api/decks", body),
  joinDeck: (code: string, guest_id: string | null, nickname: string) =>
    post<Deck>(`/api/decks/${code}/join`, { guest_id: guest_id ?? undefined, nickname }),
  deckHome: async (code: string) => normaliseDeckHome(await get<DeckHomeResponse>(`/api/decks/${code}`)),
  deckElements: async (code: string) => normaliseElements(await get<ElementsResponse>(`/api/decks/${code}/elements`)),
  deckGrammar: (code: string, includeSynthetic = true) =>
    get<Grammar>(`/api/decks/${code}/grammar?include_synthetic=${includeSynthetic ? "true" : "false"}`),
  deckBandwidth: (code: string) => get<BandwidthPoint[]>(`/api/decks/${code}/bandwidth`),
  deckCard: (code: string, cardId: string) => get<Chain>(`/api/decks/${code}/cards/${cardId}`),

  // deck mode (T2)
  deckCompose: (code: string, body: ComposeBody & { approved_editors?: "*" | string[] }) =>
    post<Chain>(`/api/decks/${code}/cards`, body),
  deckReadQueue: (code: string, guest_id: string | null) => get<ReadTask>(`/api/decks/${code}/read?guest_id=${q(guest_id)}`),
  deckReading: (code: string, cardId: string, body: ReadingBody & { version_id: string }) =>
    post<Chain>(`/api/decks/${code}/cards/${cardId}/readings`, body),
  deckEdit: (code: string, cardId: string, body: EditBody & { version_id: string }) =>
    post<Chain>(`/api/decks/${code}/cards/${cardId}/edit`, body),
  setApprovedEditors: (code: string, cardId: string, guest_id: string, approved_editors: "*" | string[]) =>
    post<Chain>(`/api/decks/${code}/cards/${cardId}/approved_editors`, { guest_id, approved_editors }),

  // misc
  grammar: (includeSynthetic = true) => get<Grammar>(`/api/grammar?include_synthetic=${includeSynthetic ? "true" : "false"}`),
  getConfig: () => get<Config>("/api/config"),
  setConfig: (cfg: Partial<Config>) => post<Config>("/api/config", cfg),
};

/** The deck code a room lives in. Playground is "PLAY"; fall back to deck_id if the server sends no code. */
export function deckCodeOf(room: Pick<Room, "deck_id" | "deck_code">): string {
  return room.deck_code ?? (room.deck_id === "playground" ? "PLAY" : room.deck_id);
}

/** Absolute URL for an element image (the API may send a relative /static path). */
export function imageSrc(url: string | null | undefined): string | null {
  if (!url) return null;
  if (/^https?:\/\//.test(url) || url.startsWith("data:")) return url;
  return `${apiUrl()}${url.startsWith("/") ? "" : "/"}${url}`;
}


// =====================================================================================
// v5 platform client (docs/SPEC-v5.md §11, all under /api). Types live in ./types.
// =====================================================================================
import type * as V5 from "./types";

const patch = <T,>(path: string, body: unknown) => request<T>(path, { method: "PATCH", body: JSON.stringify(body) });
const del = <T,>(path: string) => request<T>(path, { method: "DELETE" });
const qs = (params: Record<string, string | number | boolean | null | undefined>) => {
  const p = Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== "");
  return p.length ? "?" + p.map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`).join("&") : "";
};

export const v5 = {
  auth: {
    guest: (nickname?: string) => post<{ user: V5.User; token?: string }>("/api/auth/guest", { nickname }),
    magic: (email: string) => post<{ login_url?: string; token?: string; sent?: boolean }>("/api/auth/magic", { email }),
    magicVerify: (token: string) => get<{ user: V5.User; token?: string }>(`/api/auth/magic/${encodeURIComponent(token)}`),
    upgrade: (email: string) => post<{ login_url?: string; token?: string; user?: V5.User }>("/api/auth/upgrade", { email }),
    logout: () => post<{ ok: boolean }>("/api/auth/logout", {}),
    // the API answers {user, decks} (and {user: null} with no session); callers get the user or null
    me: () => get<{ user: V5.User | null; decks?: unknown[] } | V5.User>("/api/me").then((x) => (x && typeof x === "object" && "user" in x ? (x as { user: V5.User | null }).user : (x as V5.User))),
    updateMe: (body: Partial<Pick<V5.User, "name" | "locale">>) => patch<V5.User>("/api/me", body),
    inbox: () => get<{ to_read: V5.Card[]; open_for_edit: V5.Card[]; requests: V5.Card[] }>("/api/me/inbox"),
    myDecks: () => get<V5.Deck[]>("/api/me/decks"),
    myActivity: () => get<V5.Activity[]>("/api/me/activity"),
  },
  baseDecks: {
    list: () => get<V5.BaseDeck[]>("/api/base-decks"),
    get: (slug: string) => get<V5.BaseDeck>(`/api/base-decks/${slug}`),
    cards: (slug: string) => get<V5.BaseCard[]>(`/api/base-decks/${slug}/cards`),
    symbols: (slug: string) => get<V5.Symbol[] | { symbols: V5.Symbol[] }>(`/api/base-decks/${slug}/symbols`).then((x) => (Array.isArray(x) ? x : (x?.symbols ?? []))),
  },
  structures: {
    list: () => get<V5.StructureTemplate[]>("/api/structure-templates"),
    get: (key: string) => get<V5.StructureTemplate>(`/api/structure-templates/${key}`),
  },
  decks: {
    create: (body: V5.DeckWizardPayload) => post<V5.Deck>("/api/decks", body),
    previewStyle: (body: { style_guide?: Partial<V5.StyleGuide>; style_from_base_deck_id?: string }) =>
      post<{ image_url?: string; job_id?: string }>("/api/decks/preview-style", body),
    list: (params: { visibility?: string; sort?: string; structure?: string; tradition?: string } = {}) => get<V5.Deck[]>(`/api/decks${qs(params)}`),
    get: (idOrSlug: string, shareToken?: string | null) => get<V5.Deck>(`/api/decks/${idOrSlug}${qs({ share_token: shareToken })}`),
    update: (id: string, body: Partial<V5.Deck> & { settings?: Partial<V5.DeckSettings>; style_guide?: Partial<V5.StyleGuide> }) => patch<V5.Deck>(`/api/decks/${id}`, body),
    remove: (id: string) => del<{ ok: boolean }>(`/api/decks/${id}`),
    fork: (id: string, body: { name?: string; visibility?: V5.Visibility } = {}) => post<V5.Deck>(`/api/decks/${id}/fork`, body),
    lineage: (id: string) => get<{ ancestors: V5.LineageRef[]; children: V5.LineageRef[]; origin: V5.DeckOrigin }>(`/api/decks/${id}/lineage`),
    syncFromParent: (id: string, body: { symbols?: string[]; versions?: string[] } = {}) => post<{ ok: boolean }>(`/api/decks/${id}/sync-from-parent`, body),
    activity: (id: string) => get<V5.Activity[]>(`/api/decks/${id}/activity`),
    exportZip: (id: string) => get<V5.Job>(`/api/decks/${id}/export`),
    coherence: (id: string) => get<V5.Coherence7>(`/api/decks/${id}/coherence`),
    grammar: (id: string, includeSynthetic = true) => get<V5.Grammar>(`/api/decks/${id}/grammar${qs({ include_synthetic: includeSynthetic })}`),
    reinterpret: (id: string, body: { base_deck_id: string; positions?: string[]; assign_makers?: boolean }) => post<V5.Job>(`/api/decks/${id}/reinterpret`, body),
    readNext: (id: string) => get<{ empty?: boolean; card_id?: string; version?: V5.Version; previous_axes?: V5.Axes8 | null }>(`/api/decks/${id}/read/next`),
    sessions: (id: string) => get<V5.Session[]>(`/api/decks/${id}/sessions`),
    createSession: (id: string, body: { mode: "reading" | "relay"; nickname?: string; settings?: Partial<V5.Session["settings"]> }) =>
      post<V5.SessionView>(`/api/decks/${id}/sessions`, body),
    upstreamProposals: (id: string) => get<V5.UpstreamProposal[]>(`/api/decks/${id}/upstream-proposals`),
    createUpstreamProposal: (id: string, body: { kind: "version" | "symbol"; version_id?: string; symbol_id?: string; note: string }) =>
      post<V5.UpstreamProposal>(`/api/decks/${id}/upstream-proposals`, body),
  },
  members: {
    list: (deckId: string) => get<V5.Membership[]>(`/api/decks/${deckId}/members`),
    add: (deckId: string, body: { user_id?: string; email?: string; role: V5.DeckRole }) => post<V5.Membership>(`/api/decks/${deckId}/members`, body),
    update: (deckId: string, userId: string, body: { role?: V5.DeckRole; remove?: boolean }) => patch<V5.Membership | { ok: boolean }>(`/api/decks/${deckId}/members/${userId}`, body),
    invitations: (deckId: string) => get<V5.Invitation[]>(`/api/decks/${deckId}/invitations`),
    invite: (deckId: string, body: { email?: string; role: V5.DeckRole; link?: boolean }) => post<V5.Invitation>(`/api/decks/${deckId}/invitations`, body),
    accept: (token: string) => post<V5.Membership>(`/api/invitations/${token}/accept`, {}),
  },
  symbols: {
    list: (deckId: string, status?: V5.SymbolStatus) => get<V5.Symbol[]>(`/api/decks/${deckId}/symbols${qs({ status })}`),
    get: (sid: string) => get<V5.Symbol & { cards?: { card_id: string; position_key?: string; effect?: V5.Axes8; angle?: number }[] }>(`/api/symbols/${sid}`),
    add: (deckId: string, body: Record<string, unknown>) => post<V5.Symbol>(`/api/decks/${deckId}/symbols`, body),
    update: (sid: string, body: Record<string, unknown>) => patch<V5.Symbol>(`/api/symbols/${sid}`, body),
    merge: (sid: string, intoSymbolId: string) => post<V5.Symbol>(`/api/symbols/${sid}/merge`, { into_symbol_id: intoSymbolId }),
    retire: (sid: string) => post<V5.Symbol>(`/api/symbols/${sid}/retire`, {}),
    importFromBase: (deckId: string, body: { base_deck_slug: string; symbol_keys: string[] }) => post<{ imported: number; symbols?: V5.Symbol[] }>(`/api/decks/${deckId}/symbols/import`, body),
    proposals: (deckId: string, status?: string) => get<V5.SymbolProposal[]>(`/api/decks/${deckId}/symbol-proposals${qs({ status })}`),
    propose: (deckId: string, body: Record<string, unknown>) => post<V5.SymbolProposal>(`/api/decks/${deckId}/symbol-proposals`, body),
    decide: (pid: string, body: { status: "approved" | "declined"; decision_note?: string }) => patch<V5.SymbolProposal>(`/api/symbol-proposals/${pid}`, body),
  },
  cards: {
    list: (deckId: string, params: { filter?: string } = {}) => get<V5.Card[]>(`/api/decks/${deckId}/cards${qs(params)}`),
    create: (deckId: string, body: { position_key?: string; title?: string }) => post<V5.Card>(`/api/decks/${deckId}/cards`, body),
    get: (cid: string) => get<V5.Card>(`/api/cards/${cid}`),
    update: (cid: string, body: Record<string, unknown>) => patch<V5.Card>(`/api/cards/${cid}`, body),
    openForEdits: (cid: string) => post<V5.Card>(`/api/cards/${cid}/open`, {}),
    archive: (cid: string) => post<V5.Card>(`/api/cards/${cid}/archive`, {}),
    requestEdit: (cid: string, note: string) => post<V5.Card>(`/api/cards/${cid}/edit-requests`, { note }),
    decideRequest: (cid: string, rid: string, status: "approved" | "declined") => patch<V5.Card>(`/api/cards/${cid}/edit-requests/${rid}`, { status }),
    versions: (cid: string) => get<V5.Version[] | { versions: V5.Version[]; edges?: unknown[] }>(`/api/cards/${cid}/versions`).then((x) => (Array.isArray(x) ? x : (x?.versions ?? []))),
    generate: (cid: string, body: Record<string, unknown>) => post<V5.Job>(`/api/cards/${cid}/generate`, body),
    edit: (cid: string, body: Record<string, unknown>) => post<V5.Job>(`/api/cards/${cid}/edit`, body),
    branch: (cid: string, body: { from_version_id: string; branch_key: string }) => post<V5.Card>(`/api/cards/${cid}/branches`, body),
  },
  versions: {
    choose: (vid: string, index: number) => post<V5.Version>(`/api/versions/${vid}/choose`, { candidate_index: index }),
    restore: (vid: string, note?: string) => post<V5.Version>(`/api/versions/${vid}/restore`, { note }),
    compare: (vid: string, vid2: string) => get<{ heatmap_url?: string; fidelity?: number; containment?: number; a: V5.Version; b: V5.Version }>(`/api/versions/${vid}/compare/${vid2}`),
    reveal: (vid: string) => get<Record<string, unknown>>(`/api/versions/${vid}/reveal`),
    verdict: (vid: string) => get<V5.Verdict>(`/api/versions/${vid}/verdict`),
    submitReading: (vid: string, body: { axes: V5.Axes8; free_text?: string; latency_ms?: number }) => post<{ ok: boolean; reveal?: unknown }>(`/api/versions/${vid}/readings`, body),
  },
  sessions: {
    join: (code: string, nickname: string) => post<V5.SessionView>("/api/sessions/join", { code, nickname }),
    get: (sid: string) => get<V5.SessionView>(`/api/sessions/${sid}`),
    start: (sid: string) => post<V5.SessionView>(`/api/sessions/${sid}/start`, {}),
    advance: (sid: string) => post<V5.SessionView>(`/api/sessions/${sid}/advance`, {}),
    end: (sid: string) => post<V5.SessionView>(`/api/sessions/${sid}/end`, {}),
    choose: (sid: string, card_id: string) => post<V5.SessionView>(`/api/sessions/${sid}/choose`, { card_id }),
    submit: (sid: string, rid: string, body: { axes: V5.Axes8; free_text?: string; latency_ms?: number }) =>
      post<V5.SessionView>(`/api/sessions/${sid}/rounds/${rid}/submit`, body),
    edit: (sid: string, body: { op: string; symbol_id?: string | null; to_symbol_id?: string | null; placement?: string | null; bet_axis: number; rationale?: string }) =>
      post<{ job: V5.Job; session: V5.SessionView }>(`/api/sessions/${sid}/edit`, body),
    eventsUrl: (sid: string) => `${apiUrl()}/api/sessions/${sid}/events${getToken() ? `?token=${encodeURIComponent(getToken() as string)}` : ""}`,
  },
  jobs: {
    get: (jid: string) => get<V5.Job>(`/api/jobs/${jid}`),
    eventsUrl: (jid: string) => `${apiUrl()}/api/jobs/${jid}/events${getToken() ? `?token=${encodeURIComponent(getToken() as string)}` : ""}`,
  },
  notifications: {
    list: () => get<V5.Notification[]>("/api/notifications"),
    markRead: (nid: string) => patch<V5.Notification>(`/api/notifications/${nid}`, { read: true }),
  },
  upstream: {
    decide: (pid: string, body: { status: "accepted" | "declined"; decision_note?: string }) => patch<V5.UpstreamProposal>(`/api/upstream-proposals/${pid}`, body),
  },
};
