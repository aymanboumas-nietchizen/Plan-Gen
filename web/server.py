"""The web studio's HTTP surface: Starlette, served by uvicorn.

Both already ship with the `studio` extra (Streamlit depends on them), so this
adds no dependency. The server is stateless as far as the page is concerned —
the page owns the brief and the gallery and survives a reload from its own
storage — and keeps only a cache of the files each option can download, keyed
by (brief, seed, effort). A cache miss regenerates: the same seed is the same
plan, so a download never depends on the server having stayed up.

Generation is CPU-bound Python, so it runs in a process pool: the page fires one
request per option and each card fills in as its own request returns.

Routes follow the project's hierarchy — building, storey, unit — although only
the unit level generates today; `/api/storey/generate` answers 501 and says why.
"""

from __future__ import annotations

import asyncio
import json
import logging
import multiprocessing
import re
from collections import OrderedDict
from concurrent.futures import Executor, ProcessPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Callable

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from web import engine, project

STATIC = Path(__file__).parent / "static"
CACHE_SIZE = 256
log = logging.getLogger("planfgen.web")


class _Cache:
    """The last `CACHE_SIZE` options, most recent last."""

    def __init__(self, size: int = CACHE_SIZE) -> None:
        self.size = size
        self.items: OrderedDict[str, engine.Option] = OrderedDict()

    def get(self, key: str) -> engine.Option | None:
        option = self.items.get(key)
        if option is not None:
            self.items.move_to_end(key)
        return option

    def put(self, key: str, option: engine.Option) -> None:
        self.items[key] = option
        self.items.move_to_end(key)
        while len(self.items) > self.size:
            self.items.popitem(last=False)


def _error(message: str, status: int = 422) -> JSONResponse:
    return JSONResponse({"error": message}, status_code=status)


async def _body(request: Request) -> dict:
    try:
        body = await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise engine.BriefError("La requête n'est pas du JSON.") from None
    if not isinstance(body, dict):
        raise engine.BriefError("La requête doit être un objet JSON.")
    return body


def _run_args(body: dict) -> tuple[dict, int, int]:
    spec = body.get("spec")
    if not isinstance(spec, dict):
        raise engine.BriefError("La requête ne contient pas de programme (« spec »).")
    try:
        seed = int(body.get("seed", 1))
        iterations = int(body.get("iterations", 200))
    except (TypeError, ValueError):
        raise engine.BriefError("La graine et l'effort doivent être des entiers.") from None
    if not 0 <= seed <= 10**6:
        raise engine.BriefError("La graine doit être entre 0 et 1 000 000.")
    if not 20 <= iterations <= engine.MAX_ITERATIONS:
        raise engine.BriefError(f"L'effort doit être entre 20 et {engine.MAX_ITERATIONS} itérations.")
    return spec, seed, iterations


def create_app(executor_factory: Callable[[], Executor] | None = None) -> Starlette:
    """The app. `executor_factory` is a process pool unless a test says otherwise."""
    factory = executor_factory or _process_pool
    cache = _Cache()

    @asynccontextmanager
    async def lifespan(app: Starlette):
        app.state.executor = factory()
        if isinstance(app.state.executor, ProcessPoolExecutor):
            # Start every worker now, while the page loads, not on the first Générer.
            loop = asyncio.get_running_loop()
            for _ in range(engine.worker_count()):
                loop.run_in_executor(app.state.executor, engine.warm)
        try:
            yield
        finally:
            app.state.executor.shutdown(wait=False, cancel_futures=True)

    async def option_for(request: Request, spec: dict, seed: int, iterations: int) -> engine.Option:
        key = engine.key_of(spec, seed, iterations)
        option = cache.get(key)
        if option is None:
            engine.build(spec)  # refuse a bad brief here, with its message, not in a worker
            loop = asyncio.get_running_loop()
            option = await loop.run_in_executor(
                request.app.state.executor, engine.run, spec, seed, iterations
            )
            cache.put(key, option)
        return option

    async def index(request: Request) -> Response:
        return FileResponse(STATIC / "index.html")

    async def favicon(request: Request) -> Response:
        return Response(status_code=204)  # no icon, and no 404 in the console

    async def meta(request: Request) -> Response:
        return JSONResponse(engine.meta() | {"storey_kinds": project.STOREY_KINDS})

    # --- building level: the project, and what can be said of it without a plate engine

    async def project_default(request: Request) -> Response:
        return JSONResponse(project.default_project())

    async def building_summary(request: Request) -> Response:
        try:
            body = await _body(request)
            return JSONResponse(project.summary(body.get("project")))
        except engine.BriefError as exc:
            return _error(str(exc))

    # --- storey level: reserved, and honest about it

    async def storey_generate(request: Request) -> Response:
        return _error(project.PLATE_PENDING, 501)

    # --- unit level: the only level the engine generates today

    async def default(request: Request) -> Response:
        key = request.query_params.get("preset", "F3")
        profile = request.query_params.get("profile", "economique")
        if key not in engine.PRESETS:
            return _error(f"Typologie inconnue : {key!r}.", 404)
        return JSONResponse(engine.default_spec(key, profile))

    async def check(request: Request) -> Response:
        try:
            body = await _body(request)
            return JSONResponse(engine.check(body.get("spec") or {}))
        except engine.BriefError as exc:
            return _error(str(exc))

    async def generate(request: Request) -> Response:
        try:
            spec, seed, iterations = _run_args(await _body(request))
            option = await option_for(request, spec, seed, iterations)
        except engine.BriefError as exc:
            return _error(str(exc))
        except Exception as exc:  # the engine failing is a message, not a blank card
            log.exception("generation failed")
            return _error(f"Erreur du moteur : {type(exc).__name__}: {exc}", 500)
        return JSONResponse(option.payload)

    async def export(request: Request) -> Response:
        try:
            body = await _body(request)
            spec, seed, iterations = _run_args(body)
            option = await option_for(request, spec, seed, iterations)
        except engine.BriefError as exc:
            return _error(str(exc))
        if not option.payload["ok"]:
            return _error("Cette option n'a pas de plan à exporter.", 409)

        stem = _filename(spec, seed)
        fmt = body.get("format", "dxf")
        if fmt == "dxf":
            return Response(
                option.dxf,
                media_type="application/dxf",
                headers={"Content-Disposition": f'attachment; filename="{stem}.dxf"'},
            )
        if fmt == "gh":
            document = {k: v for k, v in option.payload["document"].items() if k != "solids"}
            return Response(
                json.dumps(document, indent=2, ensure_ascii=False),
                media_type="application/json",
                headers={"Content-Disposition": f'attachment; filename="{stem}.gh.json"'},
            )
        return _error(f"Format inconnu : {fmt!r}. Formats : dxf, gh.")

    return Starlette(
        routes=[
            Route("/", index),
            Route("/favicon.ico", favicon),
            Route("/api/meta", meta),
            Route("/api/project/default", project_default),
            Route("/api/building/summary", building_summary, methods=["POST"]),
            Route("/api/storey/generate", storey_generate, methods=["POST"]),
            Route("/api/unit/default", default),
            Route("/api/unit/check", check, methods=["POST"]),
            Route("/api/unit/generate", generate, methods=["POST"]),
            Route("/api/unit/export", export, methods=["POST"]),
            Mount("/static", StaticFiles(directory=STATIC), name="static"),
        ],
        lifespan=lifespan,
    )


def _process_pool() -> ProcessPoolExecutor:
    """Workers started with `spawn`, on every platform.

    Windows only has spawn. On Linux the default is fork, and a worker forked
    after uvicorn has bound its port inherits the listening socket and uvicorn's
    SIGTERM handler: stopping the server left the workers alive, ignoring the
    signal and holding the port (measured 2026-09-29). Spawned workers inherit
    neither, and exit when the server's end of their pipe closes.
    """
    return ProcessPoolExecutor(engine.worker_count(), mp_context=multiprocessing.get_context("spawn"))


def _filename(spec: dict, seed: int) -> str:
    raw = f"planfgen_{spec.get('typology', 'plan')}_{spec.get('profile', '')}_graine{seed}"
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", raw)
