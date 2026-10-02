"""Local Tess shell. Imports Merit. Does not bind a public host."""

import asyncio
import http.client
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qsl

import atlas_merit
from atlas_merit import fetch, track
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.templating import Jinja2Templates

from atlas_alfa import draft, ledger

HOST = "127.0.0.1"
CSP = "default-src 'self'"
REMINDER_KINDS = ("email", "teste")
EXCERPT_CHARS = 600

_TEMPLATES = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
_HTMX = Path(atlas_merit.__file__).resolve().parent / "serve" / "static" / "htmx.min.js"


def _form(body: bytes) -> dict[str, str]:
    # ponytail: urlencoded only, same as Merit serve. Avoids python-multipart.
    return dict(parse_qsl(body.decode(errors="replace")))


def _partial(request: Request) -> bool:
    return request.headers.get("hx-request") == "true"


def create_app(complete=draft.AUTO) -> FastAPI:
    if complete is draft.AUTO:
        complete = draft.complete_from_env()
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = CSP
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.get("/static/htmx.min.js")
    def htmx_js():
        # ponytail: reuse Merit's vendored htmx. Copy the file if Merit drops it.
        return FileResponse(_HTMX)

    @app.get("/")
    def index(request: Request):
        rows = ledger.active_rows(ledger.db_path())
        return _TEMPLATES.TemplateResponse(request, "index.html", {"rows": rows})

    def _found(app_id: int):
        path = ledger.db_path()
        found = ledger.row(path, app_id)
        return path, found

    def _context(
        path: str,
        app_id: int,
        found,
        error: str | None = None,
        draft_text: str | None = None,
        draft_error: str | None = None,
        recruiter_error: str | None = None,
        reminder_error: str | None = None,
        research_error: str | None = None,
    ) -> dict:
        research = ledger.entries(path, app_id, "pesquisa")
        return {
            "app_id": app_id,
            "title": found["title"],
            "company": found["company"],
            "label": ledger.LABELS.get(found["status"], found["status"]),
            "thread_entries": ledger.entries(path, app_id, "thread"),
            "recruiter_entries": ledger.entries(path, app_id, "recrutador"),
            "reminder_entries": ledger.entries(path, app_id, "lembrete"),
            "reminder_kinds": REMINDER_KINDS,
            "research": research[-1][1] if research else None,
            "error": error,
            "draft_text": draft_text,
            "draft_error": draft_error,
            "recruiter_error": recruiter_error,
            "reminder_error": reminder_error,
            "research_error": research_error,
        }

    @app.get("/processos/{app_id}")
    def processo(request: Request, app_id: int):
        path, found = _found(app_id)
        if found is None:
            return _TEMPLATES.TemplateResponse(request, "missing.html", {}, status_code=404)
        return _TEMPLATES.TemplateResponse(
            request, "processo.html", _context(path, app_id, found)
        )

    @app.post("/processos/{app_id}/thread")
    async def paste_thread(request: Request, app_id: int):
        path, found = _found(app_id)
        if found is None:
            return _TEMPLATES.TemplateResponse(request, "missing.html", {}, status_code=404)
        text = _form(await request.body()).get("text", "")
        error = None
        try:
            track.log(path, app_id, text, file="thread", dossier_root=ledger.dossier_root())
        except track.TrackError:
            error = "Texto vazio."
        context = _context(path, app_id, found, error=error)
        template = "_thread.html" if _partial(request) else "processo.html"
        return _TEMPLATES.TemplateResponse(request, template, context)

    @app.post("/processos/{app_id}/rascunho")
    async def rascunho(request: Request, app_id: int):
        path, found = _found(app_id)
        if found is None:
            return _TEMPLATES.TemplateResponse(request, "missing.html", {}, status_code=404)
        body = "\n\n".join(text for _, text in ledger.entries(path, app_id, "thread")).strip()
        draft_text = None
        draft_error = None
        if not body:
            draft_error = draft.NO_THREAD
        elif complete is None:
            draft_error = draft.NO_MODEL
        else:
            prompt = draft.prompt_for(body, title=found["title"], company=found["company"])
            raw = await asyncio.to_thread(complete, prompt)
            vetted = draft.vet(raw)
            if vetted is None:
                draft_error = draft.BLOCKED
            else:
                draft_text = vetted
        context = _context(path, app_id, found, draft_text=draft_text, draft_error=draft_error)
        template = "_draft.html" if _partial(request) else "processo.html"
        return _TEMPLATES.TemplateResponse(request, template, context)

    @app.post("/processos/{app_id}/status")
    async def change_status(request: Request, app_id: int):
        path, found = _found(app_id)
        if found is None:
            return _TEMPLATES.TemplateResponse(request, "missing.html", {}, status_code=404)
        status = _form(await request.body()).get("status", "")
        error = None
        code = 200
        try:
            track.set_status(path, app_id, status)
            found = ledger.row(path, app_id)
        except track.TrackError:
            error = "Status inválido."
            code = 422
        return _TEMPLATES.TemplateResponse(
            request, "processo.html", _context(path, app_id, found, error=error), status_code=code
        )

    @app.post("/processos/{app_id}/recrutador")
    async def recruiter(request: Request, app_id: int):
        path, found = _found(app_id)
        if found is None:
            return _TEMPLATES.TemplateResponse(request, "missing.html", {}, status_code=404)
        fields = _form(await request.body())
        nome = fields.get("nome", "").strip()
        url = fields.get("url", "").strip()
        error = None
        if not nome or not url.startswith("https://"):
            error = "Nome e URL https:// obrigatorios."
        else:
            entry = f"nome: {nome}\nurl: {url}"
            track.log(path, app_id, entry, file="recrutador", dossier_root=ledger.dossier_root())
        return _TEMPLATES.TemplateResponse(
            request,
            "processo.html",
            _context(path, app_id, found, recruiter_error=error),
            status_code=422 if error else 200,
        )

    @app.post("/processos/{app_id}/pesquisa")
    async def research(request: Request, app_id: int):
        path, found = _found(app_id)
        if found is None:
            return _TEMPLATES.TemplateResponse(request, "missing.html", {}, status_code=404)
        fields = _form(await request.body())
        url = fields.get("url", "").strip()
        rotulo = fields.get("rotulo", "").strip()
        error = None
        code = 200
        if not rotulo or not url.startswith("https://"):
            error = "Rotulo e URL https:// obrigatorios."
            code = 422
        else:
            try:
                text = await asyncio.to_thread(fetch.fetch_posting, url, 10)
            except (OSError, ValueError, http.client.HTTPException):
                text = ""
            excerpt = text.strip()[:EXCERPT_CHARS]
            if excerpt:
                entry = f"rotulo: {rotulo}\nurl: {url}\n\n{excerpt}"
                track.log(path, app_id, entry, file="pesquisa", dossier_root=ledger.dossier_root())
            else:
                error = "Pesquisa indisponivel."
        return _TEMPLATES.TemplateResponse(
            request,
            "processo.html",
            _context(path, app_id, found, research_error=error),
            status_code=code,
        )

    @app.post("/processos/{app_id}/lembrete")
    async def reminder(request: Request, app_id: int):
        path, found = _found(app_id)
        if found is None:
            return _TEMPLATES.TemplateResponse(request, "missing.html", {}, status_code=404)
        fields = _form(await request.body())
        kind = fields.get("kind", "")
        quando = fields.get("quando", "").strip()
        dados = fields.get("dados", "").strip()
        error = None
        if kind not in REMINDER_KINDS:
            error = "Tipo invalido."
        else:
            try:
                datetime.fromisoformat(quando)
            except ValueError:
                error = "Data obrigatoria."
        if error is None:
            entry = f"kind: {kind}\nquando: {quando}\ndados: {dados or '-'}"
            track.log(path, app_id, entry, file="lembrete", dossier_root=ledger.dossier_root())
        return _TEMPLATES.TemplateResponse(
            request,
            "processo.html",
            _context(path, app_id, found, reminder_error=error),
            status_code=422 if error else 200,
        )

    return app
