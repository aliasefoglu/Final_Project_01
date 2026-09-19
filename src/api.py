from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from typing import Literal

import markdown
from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from src.config import settings
from src.core.digest_builder import digest_path
from src.models import TopicEnum, User
from src.security import hash_password, verify_password
from src.storage.repository import Repository

_BASE_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=str(_BASE_DIR / "templates"))
repository = Repository()


@asynccontextmanager
async def lifespan(_: FastAPI):
    await repository.connect()
    await repository.init_schema()
    yield
    await repository.close()


app = FastAPI(title="NewsBrief", lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=settings.session_secret_key)
app.mount(
    "/static",
    StaticFiles(directory=str(_BASE_DIR / "static")),
    name="static",
)


def current_user_id(request: Request) -> str | None:
    return request.session.get("user_id")


def require_login(request: Request) -> str:
    user_id = current_user_id(request)

    if user_id is None:
        raise HTTPException(
            status_code=303,
            headers={"Location": "/login"},
        )

    return user_id


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> RedirectResponse:
    destination = "/preferences" if current_user_id(request) else "/login"
    return RedirectResponse(destination, status_code=303)


@app.get("/signup", response_class=HTMLResponse)
async def signup_form(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "signup.html",
        {"error": None},
    )


@app.post("/signup")
async def signup_submit(
    request: Request,
    user_id: str = Form(...),
    password: str = Form(...),
    password_confirm: str = Form(...),
):
    user_id = user_id.strip().lower()

    if not user_id or len(password) < 8:
        return templates.TemplateResponse(
            request,
            "signup.html",
            {
                "error": (
                    "Username is required and password must be "
                    "at least 8 characters."
                )
            },
            status_code=400,
        )

    if password != password_confirm:
        return templates.TemplateResponse(
            request,
            "signup.html",
            {"error": "Passwords do not match."},
            status_code=400,
        )

    if await repository.get_account(user_id) is not None:
        return templates.TemplateResponse(
            request,
            "signup.html",
            {"error": "That username is already taken."},
            status_code=400,
        )

    await repository.save_user(User(user_id=user_id))
    await repository.create_account(user_id, hash_password(password))

    request.session["user_id"] = user_id

    return RedirectResponse("/preferences", status_code=303)


@app.get("/login", response_class=HTMLResponse)
async def login_form(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "login.html",
        {"error": None},
    )


@app.post("/login")
async def login_submit(
    request: Request,
    user_id: str = Form(...),
    password: str = Form(...),
):
    user_id = user_id.strip().lower()
    account = await repository.get_account(user_id)

    if account is None or not verify_password(
        password,
        account.password_hash,
    ):
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": "Invalid username or password."},
            status_code=401,
        )

    request.session["user_id"] = user_id

    return RedirectResponse("/preferences", status_code=303)


@app.post("/logout")
async def logout(request: Request) -> RedirectResponse:
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


@app.get("/preferences", response_class=HTMLResponse)
async def preferences_form(
    request: Request,
    user_id: str = Depends(require_login),
) -> HTMLResponse:
    user = await repository.get_user(user_id) or User(user_id=user_id)

    return templates.TemplateResponse(
        request,
        "preferences.html",
        {
            "user": user,
            "all_topics": list(TopicEnum),
            "saved": False,
        },
    )


@app.post("/preferences")
async def preferences_submit(
    request: Request,
    user_id: str = Depends(require_login),
    topics: list[str] = Form(default=[]),
    excluded_sources: str = Form(default=""),
    preferred_length: Literal["short", "medium", "long"] = Form(
        default="medium"
    ),
):
    user = User(
        user_id=user_id,
        preferred_topics=[TopicEnum(topic) for topic in topics],
        excluded_sources=[
            source.strip()
            for source in excluded_sources.split(",")
            if source.strip()
        ],
        preferred_length=preferred_length,
    )

    await repository.save_user(user)

    return templates.TemplateResponse(
        request,
        "preferences.html",
        {
            "user": user,
            "all_topics": list(TopicEnum),
            "saved": True,
        },
    )


@app.get("/digest", response_class=HTMLResponse)
async def latest_digest(
    request: Request,
    user_id: str = Depends(require_login),
) -> HTMLResponse:
    path = digest_path(user_id, on=date.today())
    content_html = None

    if path.exists():
        markdown_text = path.read_text(encoding="utf-8")
        content_html = markdown.markdown(
            markdown_text,
            extensions=["extra", "sane_lists", "nl2br"],
        )

    return templates.TemplateResponse(
        request,
        "digest.html",
        {
            "content_html": content_html,
            "user_id": user_id,
        },
    )