"""PIXIE v5 API — app factory. Routers per spec §11 (all under /api), /media for local storage, jobs runner,
SSE, CORS with credentials. See docs/CONTRACT.md (v5)."""
from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

import auth as A
import jobs as J
from pixie.embed import backend_name as embed_backend
from pixie.naming import naming_backend
from pixie.store import open_store
from routers import deps
from storage import content_type_for, open_storage

HERE = os.path.dirname(os.path.abspath(__file__))
SNAPSHOT = os.environ.get("PIXIE_SNAPSHOT", os.path.join(HERE, ".pixie_state_v5.json"))
VERSION = "0.5"


def build_services() -> dict:
    """Optional engine services other streams register (imaging, measurement). Missing ones are simply absent."""
    services: dict = {}
    try:
        from pixie.imaging import pipeline  # noqa: F401  (stream E1 registers job handlers on import)
        services["imaging"] = pipeline
    except Exception as e:  # pragma: no cover
        services["imaging_error"] = f"{type(e).__name__}: {e}"
    return services


@asynccontextmanager
async def lifespan(app: FastAPI):
    store = open_store(SNAPSHOT)
    storage = open_storage()
    A.bind(store)
    deps.state["store"] = store
    deps.state["storage"] = storage
    services = build_services()
    services.update({"store": store, "storage": storage})
    deps.state["jobs"] = J.JobRunner(store, services=services)
    deps.state["services"] = services
    for hook in STARTUP_HOOKS:
        try:
            hook(deps.state)
        except Exception as e:  # never block boot on an optional hook
            print(f"[main] startup hook {getattr(hook, '__name__', hook)} failed: {type(e).__name__}: {e}")
    yield
    store.flush()


STARTUP_HOOKS: list = []  # other streams append callables(state) here (base-deck load, seeds…)

app = FastAPI(title="PIXIE", version=VERSION, lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origin_regex=".*", allow_credentials=True, allow_methods=["*"], allow_headers=["*"], expose_headers=["*"])

from routers import auth as r_auth, decks as r_decks, jobs as r_jobs, members as r_members, notifications as r_notifications, symbols as r_symbols  # noqa: E402

for r in (r_auth, r_decks, r_members, r_symbols, r_jobs, r_notifications):
    app.include_router(r.router)
for name in ("base_decks", "cards", "versions", "readings", "sessions", "forks", "measurement", "export", "admin"):
    try:
        mod = __import__(f"routers.{name}", fromlist=["router"])
        app.include_router(mod.router)
    except ImportError:
        pass
    except Exception as e:  # a broken optional router must not take the API down
        print(f"[main] router {name} not loaded: {type(e).__name__}: {e}")
try:
    from service import base_decks as _bd  # noqa: E402
    if hasattr(_bd, "on_startup"):
        STARTUP_HOOKS.append(_bd.on_startup)  # base registries first: the seeds hook needs them
except ImportError:
    pass
try:
    from service import base_decks as _bd  # noqa: E402
    if hasattr(_bd, "on_startup"):
        STARTUP_HOOKS.append(_bd.on_startup)  # base registries first: the seeds hook needs them
except ImportError:
    pass
try:
    from service import seeds as _seeds  # noqa: E402
    if hasattr(_seeds, "on_startup"):
        STARTUP_HOOKS.append(_seeds.on_startup)
except ImportError:
    pass


@app.get("/media/{key:path}")
def media(key: str, sig: str | None = None, exp: str | None = None):
    st = deps.storage()
    if not st.verify(key, sig, exp):
        raise HTTPException(403, {"code": "role_required", "detail": "signed URL required"})
    data = st.get(key)
    if data is None:
        raise HTTPException(404, "not found")
    return Response(content=data, media_type=content_type_for(key), headers={"Cache-Control": "public, max-age=31536000, immutable"})


@app.get("/api/health")
def health():
    store = deps.store()
    counts = {c: store.count(c) for c in ("users", "base_decks", "base_cards", "base_symbols", "decks", "symbols", "cards", "versions", "readings", "sessions", "jobs")}
    services = deps.state.get("services", {})
    return {"ok": True, "version": VERSION, "store": store.kind, "storage": deps.storage().kind, "worker": deps.jobs().mode,
            "embed_backend": embed_backend(), "naming_backend": naming_backend(),
            "imaging": "ready" if "imaging" in services else services.get("imaging_error", "absent"),
            "auth": {"auth0": bool(A.AUTH0_DOMAIN), "magic_link": "dev-return-url", "web_url": A.WEB_URL},
            "counts": counts}
