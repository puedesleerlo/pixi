"""PIXIE v5 domain models (spec §3, field names verbatim). Pydantic v2.

Every stored document has `id` (accepted as `_id` or `id` on input; emitted as `id`).
Derived tables (TransmissionEvent, EditEffect, Verdict, Grammar) are computed on read but
modelled here so routes return stable shapes.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Axes = list[float]
Visibility = Literal["private", "unlisted", "public"]
DeckRole = Literal["owner", "curator", "member"]
CardStatus = Literal["draft", "reading", "open", "landed", "closed", "archived"]
SymbolStatus = Literal["active", "proposed", "merged", "retired"]
Placement = Literal["any", "center", "top", "bottom", "left", "right"]
EditOp = Literal["add", "remove", "replace", "emphasize", "deemphasize", "reposition", "cosmetic"]
JobKind = Literal["generate", "edit", "tag", "fidelity", "grammar", "reinterpret_batch", "ingest_base", "export", "style_preview", "test"]
JobStatus = Literal["queued", "running", "done", "failed"]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class Doc(BaseModel):
    """Base for stored documents."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")
    id: str = ""
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)

    @model_validator(mode="before")
    @classmethod
    def _accept_mongo_id(cls, data: Any) -> Any:
        if isinstance(data, dict) and "_id" in data and not data.get("id"):
            data = {**data, "id": data["_id"]}
        return data

    def to_doc(self) -> dict:
        d = self.model_dump()
        d.pop("_id", None)
        return d


# ----------------------------------------------------------------------------- 3.1 User
class User(Doc):
    email: str | None = None
    name: str = "guest"
    avatar_url: str | None = None
    auth0_sub: str | None = None
    guest_token: str | None = None
    locale: Literal["en", "es"] = "en"
    upgraded_from_guest_at: str | None = None

    @property
    def is_guest(self) -> bool:
        return not self.email and not self.auth0_sub


# ----------------------------------------------------------------------------- 3.2 BaseDeck
class RightsChecklist(BaseModel):
    model_config = ConfigDict(extra="allow")
    source_page: str | None = None
    license_text: str | None = None
    date: str | None = None
    reviewer: str | None = None


class BaseDeck(Doc):
    slug: str
    name: str
    tradition: str = ""
    year: str | int | None = None
    origin: str = ""
    rights_note: str = ""
    source_urls: list[str] = []
    structure_template_id: str = "tarot78"
    card_count: int = 0
    status: Literal["ready", "partial", "planned"] = "planned"
    symbol_registry_id: str | None = None
    attestation_sources: list[str] = []
    rights_checklist: RightsChecklist | None = None
    registry_version: str = "v1"


class BaseCard(Doc):
    base_deck_id: str
    position_key: str
    title: str
    image_url: str
    thumb_url: str | None = None
    caption: str = ""
    attested_meaning_text: str | None = None
    attested_axes: Axes | None = None


class BaseSymbol(Doc):
    """A curated registry entry of a base deck (B2 writes these; decks import them)."""

    base_deck_id: str
    base_deck_slug: str
    key: str
    name: str
    gloss: str = ""
    tags: list[str] = []
    placement: Placement = "any"
    attested_axes: Axes | None = None
    attested_text: str | None = None
    attestations: list[dict] = []
    exemplar: dict = {}          # {image_url, bbox?, source_card}
    cards: list[str] = []        # position_keys where the symbol appears
    registry_version: str = "v1"


# ----------------------------------------------------------------------------- 3.3 Deck
class ReferenceImage(BaseModel):
    url: str
    source: Literal["base_card", "upload", "generated"] = "upload"
    weight: float = 1.0


class Border(BaseModel):
    style: str = "single line"
    color: str = "#141414"


class StyleGuide(BaseModel):
    model_config = ConfigDict(extra="allow")
    prompt_prefix: str = "black ink line art on cream paper, single figure, flat colour, early twentieth-century tarot line art"
    negative_prompt: str | None = None
    palette: list[str] = ["#f4efe6", "#141414", "#c8361e"]
    line: Literal["ink", "woodcut", "painted", "flat", "photo", "custom"] = "ink"
    reference_images: list[ReferenceImage] = []
    border: Border = Border()
    aspect: Literal["2.75x4.75", "1x1.7", "custom"] = "2.75x4.75"
    style_centroid_embedding: list[float] | None = None


class DeckOrigin(BaseModel):
    kind: Literal["blank", "base", "fork"] = "blank"
    base_deck_id: str | None = None
    forked_from_deck_id: str | None = None
    forked_at_version_snapshot_id: str | None = None


class DeckSettings(BaseModel):
    model_config = ConfigDict(extra="allow")
    who_can_create_cards: Literal["members", "curators"] = "members"
    default_editor_policy: Literal["any_member", "curators", "maker_list"] = "any_member"
    allow_branches: bool = True
    allow_forks: bool = True
    allow_guest_readers: bool = True
    ready_threshold: int = 3
    max_edits_per_card: int = 6
    candidates_per_generation: int = 2
    fidelity_threshold: float = 0.85
    style_threshold: float = 0.70
    generation_quota_month: int = 200
    live_generation_in_sessions: bool = False
    provider: str | None = None


class DeckStats(BaseModel):
    cards: int = 0
    filled_positions: int = 0
    total_positions: int | None = None
    symbols: int = 0
    readings: int = 0
    sessions: int = 0
    forks: int = 0
    coherence_index: float | None = None
    mean_fidelity: float | None = None
    needs_readings: int | None = None


class Lineage(BaseModel):
    """service.forks stores deck ids; older records may hold {deck_id, slug, name} summaries — both are accepted."""
    ancestors: list[str | dict] = []
    children: list[str | dict] = []


class Deck(Doc):
    slug: str
    name: str
    description: str = ""
    cover_url: str | None = None
    owner_id: str
    visibility: Visibility = "private"
    structure_template_id: str = "tarot78"
    style_guide: StyleGuide = StyleGuide()
    origin: DeckOrigin = DeckOrigin()
    settings: DeckSettings = DeckSettings()
    stats: DeckStats = DeckStats()
    lineage: Lineage = Lineage()
    share_token: str | None = None
    base_registry_version: str | int | None = None
    synthetic: bool = False


class Membership(Doc):
    deck_id: str
    user_id: str
    role: DeckRole = "member"
    invited_by: str | None = None
    joined_at: str = Field(default_factory=now_iso)


class Invitation(Doc):
    deck_id: str
    email: str | None = None
    link_token: str | None = None
    role: DeckRole = "member"
    expires_at: str
    accepted_at: str | None = None
    created_by: str | None = None


# ----------------------------------------------------------------------------- 3.4 Structure
class Position(BaseModel):
    key: str
    title: str
    group: str = ""
    order: int = 0


class StructureTemplate(Doc):
    key: Literal["tarot78", "majors22", "minors56", "lenormand36", "mantegna50", "free"]
    name: str
    positions: list[Position] = []


# ----------------------------------------------------------------------------- 3.6 Symbol
class Exemplar(BaseModel):
    model_config = ConfigDict(extra="allow")
    image_url: str | None = None
    origin: Literal["base_crop", "generated", "upload"] = "upload"
    source_ref: str | dict | None = None


class InheritedFrom(BaseModel):
    base_deck_id: str | None = None
    deck_id: str | None = None
    symbol_id: str


class Attestation(BaseModel):
    model_config = ConfigDict(extra="allow")
    source: str
    note: str = ""


class SymbolMeasured(BaseModel):
    coef: Axes = [0.0] * 8
    ci_low: Axes = [0.0] * 8
    ci_high: Axes = [0.0] * 8
    n_cards: int = 0
    n_readings: int = 0
    n_edits: int = 0
    coherence: Literal["consistent", "contested", "untested"] = "untested"
    declared_vs_measured: float | None = None


class Symbol(Doc):
    deck_id: str
    key: str
    name: str
    gloss: str = ""
    tags: list[str] = []
    declared_axes: Axes = [0.0] * 8
    declared_text: str = ""
    exemplar: Exemplar = Exemplar()
    placement: Placement = "any"
    origin: Literal["inherited_base", "inherited_fork", "community", "upstream"] = "community"
    inherited_from: InheritedFrom | None = None
    attestations: list[Attestation] = []
    prior_axes: Axes | None = None
    prior_source: Literal["attestation", "parent_grammar"] | None = None
    status: SymbolStatus = "active"
    merged_into_symbol_id: str | None = None
    proposed_by: str | None = None
    approved_by: str | None = None
    approved_at: str | None = None
    measured: SymbolMeasured = SymbolMeasured()


class SymbolDraft(BaseModel):
    model_config = ConfigDict(extra="allow")
    key: str | None = None
    name: str
    gloss: str = ""
    tags: list[str] = []
    declared_axes: Axes = [0.0] * 8
    declared_text: str = ""
    placement: Placement = "any"
    attestations: list[Attestation] = []
    exemplar_upload: str | None = None                 # base64 PNG/JPEG/WebP
    exemplar_from_base_card: dict | None = None        # {base_card_id, bbox: [x0,y0,x1,y1] normalised}
    exemplar_image_url: str | None = None


class SymbolProposal(Doc):
    deck_id: str
    symbol_draft: SymbolDraft
    note: str = Field(default="", max_length=280)
    status: Literal["open", "approved", "declined"] = "open"
    proposed_by: str
    decided_by: str | None = None
    decision_note: str | None = None
    symbol_id: str | None = None


# ----------------------------------------------------------------------------- 3.7 Card / Version
class Intent(BaseModel):
    statement: str = Field(max_length=140)
    axes: Axes
    embedding: list[float] | None = None


class EditRequest(BaseModel):
    id: str
    user_id: str
    note: str = Field(default="", max_length=140)
    status: Literal["open", "approved", "declined"] = "open"
    created_at: str = Field(default_factory=now_iso)


class Branch(BaseModel):
    branch_key: str
    head_version_id: str


class Card(Doc):
    deck_id: str
    position_key: str
    title: str | None = None
    maker_id: str
    intent: Intent | None = None
    approved_editors: str | list[str] = "*"
    edit_requests: list[EditRequest] = []
    status: CardStatus = "draft"
    current_version_id: str | None = None
    branches: list[Branch] = []
    tags: list[str] = []
    share_token: str | None = None
    synthetic: bool = False


class SymbolDeclared(BaseModel):
    symbol_id: str
    placement: Placement | None = None


class SymbolDetected(BaseModel):
    symbol_id: str
    salience: float = 0.5
    bbox: dict | None = None
    tagged_by: Literal["vision", "human"] = "human"
    declared_only: bool = False


class Region(BaseModel):
    x: float
    y: float
    w: float
    h: float


class Candidate(BaseModel):
    model_config = ConfigDict(extra="allow")
    image_url: str
    style_score: float | None = None
    fidelity: float | None = None
    containment: float | None = None
    heatmap_url: str | None = None
    symbols_detected: list[SymbolDetected] = []


class Generation(BaseModel):
    model_config = ConfigDict(extra="allow")
    kind: Literal["generation"] = "generation"
    mode: Literal["prompt", "reference", "reinterpret", "upload", "variation"] = "prompt"
    reference_image_url: str | None = None
    prompt_user: str = ""
    prompt_full: str = ""
    provider: str = ""
    model: str = ""
    seed: int | None = None
    candidates: list[Candidate] = []
    chosen_index: int | None = None


class Edit(BaseModel):
    model_config = ConfigDict(extra="allow")
    kind: Literal["edit"] = "edit"
    op: EditOp
    symbol_id: str | None = None
    to_symbol_id: str | None = None
    region: Region | None = None
    prompt_user: str | None = None
    prompt_full: str = ""
    provider: str = ""
    model: str = ""
    seed: int | None = None
    candidates: list[Candidate] = []
    chosen_index: int | None = None
    bet_axis: int | None = None
    rationale: str = Field(default="", max_length=140)
    editor_id: str
    counts_as_experiment: bool = True


class Checks(BaseModel):
    fidelity: float | None = None
    containment: float | None = None
    style_score: float | None = None
    symbols_missing: list[str] = []
    safety: Literal["ok", "blocked"] = "ok"


class Version(Doc):
    card_id: str
    deck_id: str
    v: int = 0
    branch_key: str = "main"
    base_version_id: str | None = None
    image_url: str
    thumb_url: str | None = None
    width: int | None = None
    height: int | None = None
    symbols_declared: list[SymbolDeclared] = []
    symbols_detected: list[SymbolDetected] = []
    how: dict = {}            # Generation | Edit (validated at write time by the cards service)
    checks: Checks = Checks()
    created_by: str = ""
    synthetic: bool = False


# ----------------------------------------------------------------------------- 3.8 Measurement
class Reading(Doc):
    deck_id: str
    card_id: str
    version_id: str
    reader_id: str
    session_id: str | None = None
    round_id: str | None = None
    free_text: str | None = Field(default=None, max_length=140)
    axes: Axes
    embedding: list[float] | None = None
    latency_ms: int | None = None
    synthetic: bool = False


class TransmissionEvent(BaseModel):
    version_id: str
    reading_id: str
    d_axes: float
    d_embed: float | None = None
    d_total: float
    inside_radius: bool


class EditEffect(BaseModel):
    version_id: str
    n_pairs: int = 0
    shift: Axes | None = None
    gap_before: Axes | None = None
    gap_after: Axes | None = None
    bet_axis: int | None = None
    bet_hit: bool | None = None
    delta_fidelity: float | None = None


class Cluster(BaseModel):
    label: str = ""
    label_by: str = "template"
    centroid: Axes
    n: int


class Verdict(BaseModel):
    version_id: str
    n: int
    V: float | None = None
    S: float | None = None
    S_null95: float | None = None
    k: int | None = None
    verdict: Literal["legible", "polysemous", "noisy", "collecting"]
    clusters: list[Cluster] = []


class Grammar(BaseModel):
    deck_id: str
    symbol_id: str
    coef: Axes
    ci_low: Axes
    ci_high: Axes
    n_readings: int
    n_edits: int = 0
    prior_axes: Axes | None = None
    drift_from_prior: float | None = None
    computed_at: str = Field(default_factory=now_iso)


# ----------------------------------------------------------------------------- 3.9 Session
class SessionSettings(BaseModel):
    read_timer: int = 60
    edit_timer: int = 45
    generation_timer: int = 40
    live_generation: bool = False
    guests_allowed: bool = True
    max_edits: int = 3


class Player(BaseModel):
    user_or_guest_id: str
    nickname: str
    role: Literal["host", "player", "reader"] = "player"
    connected: bool = True


class Session(Doc):
    deck_id: str
    code: str
    host_id: str
    mode: Literal["reading", "relay"] = "relay"
    settings: SessionSettings = SessionSettings()
    players: list[Player] = []
    state: Literal["lobby", "compose", "read", "reveal", "edit", "generating", "summary", "ended"] = "lobby"
    round_ends_at: str | None = None
    current_card_id: str | None = None
    current_version_id: str | None = None
    turn_order: list[str] = []
    turn_index: int = 0


class Score(BaseModel):
    user_id: str
    points: int
    reason: str


class Round(Doc):
    session_id: str
    kind: Literal["read", "edit"]
    card_id: str
    version_id: str
    maker_or_editor_id: str
    started_at: str = Field(default_factory=now_iso)
    ended_at: str | None = None
    readings: list[str] = []
    effect: EditEffect | None = None
    scores: list[Score] = []


# ----------------------------------------------------------------------------- 3.10 Forks
class ForkSnapshot(Doc):
    source_deck_id: str
    target_deck_id: str
    taken_at: str = Field(default_factory=now_iso)
    copied: dict = {"symbols": 0, "cards": 0, "style": True, "structure": True}


class UpstreamProposal(Doc):
    from_deck_id: str
    to_deck_id: str
    kind: Literal["version", "symbol"]
    version_id: str | None = None
    symbol_id: str | None = None
    note: str = Field(default="", max_length=280)
    status: Literal["open", "accepted", "declined"] = "open"
    proposed_by: str | None = None
    decided_by: str | None = None
    decision_note: str | None = None
    result_ref: str | None = None


# ----------------------------------------------------------------------------- 3.11 Jobs etc.
class Job(Doc):
    kind: str
    deck_id: str | None = None
    payload: dict = {}
    status: JobStatus = "queued"
    progress: float = 0.0
    note: str | None = None
    result: Any = None
    error: str | None = None
    attempts: int = 0
    created_by: str | None = None
    idempotency_key: str | None = None
    started_at: str | None = None
    finished_at: str | None = None


class Notification(Doc):
    user_id: str
    kind: str
    deck_id: str | None = None
    card_id: str | None = None
    text: str
    read_at: str | None = None


class Activity(Doc):
    deck_id: str
    actor_id: str | None = None
    kind: str
    refs: dict = {}


# ----------------------------------------------------------------------------- request bodies
class MagicBody(BaseModel):
    email: str
    name: str | None = None
    locale: Literal["en", "es"] | None = None


class UpgradeBody(BaseModel):
    email: str
    name: str | None = None


class DeckCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    description: str = ""
    visibility: Visibility = "private"
    origin: DeckOrigin = DeckOrigin()
    structure_template_id: str | None = None
    style_guide: StyleGuide | None = None
    style_from_base_deck_id: str | None = None
    import_symbols: list[str] | None = None            # base symbol keys; None = all, [] = none
    card_mode: Literal["inherit", "reference"] = "inherit"
    invites: list[dict] = []                             # [{email, role}]
    settings: DeckSettings | None = None


class DeckPatch(BaseModel):
    name: str | None = None
    description: str | None = None
    cover_url: str | None = None
    visibility: Visibility | None = None
    structure_template_id: str | None = None
    style_guide: StyleGuide | None = None
    settings: DeckSettings | None = None
    owner_id: str | None = None                         # transfer (owner only)


class MemberAdd(BaseModel):
    user_id: str | None = None
    email: str | None = None
    role: DeckRole = "member"


class MemberPatch(BaseModel):
    role: DeckRole


class InvitationCreate(BaseModel):
    email: str | None = None
    role: DeckRole = "member"
    expires_in_days: int = 14


class SymbolPatch(BaseModel):
    name: str | None = None
    gloss: str | None = None
    tags: list[str] | None = None
    declared_axes: Axes | None = None
    declared_text: str | None = None
    placement: Placement | None = None
    attestations: list[Attestation] | None = None
    exemplar_upload: str | None = None
    exemplar_from_base_card: dict | None = None


class MergeBody(BaseModel):
    into_symbol_id: str


class ImportBody(BaseModel):
    base_deck_slug: str
    symbol_keys: list[str] | None = None


class ProposalCreate(BaseModel):
    symbol_draft: SymbolDraft
    note: str = Field(default="", max_length=280)


class ProposalDecision(BaseModel):
    action: Literal["approve", "decline"]
    decision_note: str | None = None


class NotificationPatch(BaseModel):
    read: bool = True


class ForkBody(BaseModel):
    name: str | None = None
    visibility: Visibility = "private"
