"""Sign in with Microsoft Entra ID (OpenID Connect, authorisation code flow with PKCE).

Configure (backend/.env), after registering an app in Entra ID with the redirect address below:
    ENTRA_TENANT_ID      your directory (tenant) id
    ENTRA_CLIENT_ID      the app registration's application (client) id
    ENTRA_CLIENT_SECRET  a client secret of that registration
    ENTRA_REDIRECT_URI   https://<your server>/api/v1/auth/entra/callback
    ENTRA_ALLOW_PASSWORD true/false: whether password sign-in stays available (default true)

Rules:
- Only people who already have an active account sign in: Control Tower does not create accounts, so
  roles and units stay decided by administrators. The first Microsoft sign-in links the account by its
  email (the token's email or preferred_username); after that the account is matched by its Entra object
  id, so a renamed email still works.
- The ID token's signature is checked against Microsoft's published keys, and its issuer, audience,
  expiry and nonce are checked. Sign-ins are audited like password sign-ins (source "integration").
"""
import base64
import hashlib
import json
import secrets
import time
import urllib.parse
import urllib.request

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from flask import current_app, session
from sqlalchemy import func, select

from app.core.errors import Unauthorized
from app.core.models import utcnow
from app.extensions import db
from app.modules.auth.models import User

AUTHORITY = "https://login.microsoftonline.com"
SESSION_KEY = "entra_flow"
_JWKS_CACHE: dict = {}


def enabled() -> bool:
    c = current_app.config
    return bool(c.get("ENTRA_TENANT_ID") and c.get("ENTRA_CLIENT_ID") and c.get("ENTRA_CLIENT_SECRET"))


def password_allowed() -> bool:
    return not enabled() or bool(current_app.config.get("ENTRA_ALLOW_PASSWORD", True))


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def redirect_uri() -> str:
    c = current_app.config
    return c.get("ENTRA_REDIRECT_URI") or f"{(c.get('APP_BASE_URL') or '').rstrip('/')}/api/v1/auth/entra/callback"


def safe_next(target: str | None) -> str:
    """Only a path on this site (never another site) may follow sign-in."""
    if target and target.startswith("/") and not target.startswith("//") and "\\" not in target:
        return target
    return "/pages/home.html"


def authorize_url(next_path: str | None) -> str:
    c = current_app.config
    verifier = _b64url(secrets.token_bytes(32))
    state, nonce = secrets.token_urlsafe(24), secrets.token_urlsafe(24)
    session[SESSION_KEY] = {"state": state, "nonce": nonce, "verifier": verifier, "next": safe_next(next_path),
                            "at": int(time.time())}
    params = {
        "client_id": c["ENTRA_CLIENT_ID"], "response_type": "code", "redirect_uri": redirect_uri(),
        "response_mode": "query", "scope": "openid profile email", "state": state, "nonce": nonce,
        "code_challenge": _b64url(hashlib.sha256(verifier.encode()).digest()), "code_challenge_method": "S256",
        "prompt": "select_account",
    }
    return f"{AUTHORITY}/{c['ENTRA_TENANT_ID']}/oauth2/v2.0/authorize?{urllib.parse.urlencode(params)}"


# ---------------------------------------------------------------------- calls to Microsoft (replaced in tests)
def _post_token(code: str, verifier: str) -> dict:
    c = current_app.config
    body = urllib.parse.urlencode({
        "client_id": c["ENTRA_CLIENT_ID"], "client_secret": c["ENTRA_CLIENT_SECRET"], "grant_type": "authorization_code",
        "code": code, "redirect_uri": redirect_uri(), "code_verifier": verifier, "scope": "openid profile email",
    }).encode()
    req = urllib.request.Request(f"{AUTHORITY}/{c['ENTRA_TENANT_ID']}/oauth2/v2.0/token", data=body, method="POST",
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310 — fixed Microsoft address
        return json.loads(resp.read())


def _jwks() -> dict:
    tenant = current_app.config["ENTRA_TENANT_ID"]
    cached = _JWKS_CACHE.get(tenant)
    if cached and cached[0] > time.time():
        return cached[1]
    with urllib.request.urlopen(f"{AUTHORITY}/{tenant}/discovery/v2.0/keys", timeout=10) as resp:  # noqa: S310
        keys = json.loads(resp.read())
    _JWKS_CACHE[tenant] = (time.time() + 3600, keys)
    return keys


# ---------------------------------------------------------------------- the ID token
def verify_id_token(token: str, nonce: str) -> dict:
    c = current_app.config
    try:
        head_b64, body_b64, sig_b64 = token.split(".")
        header = json.loads(_b64url_decode(head_b64))
        claims = json.loads(_b64url_decode(body_b64))
        signature = _b64url_decode(sig_b64)
    except (ValueError, TypeError) as exc:
        raise Unauthorized("Microsoft sign-in failed: the token could not be read") from exc
    if header.get("alg") != "RS256":
        raise Unauthorized("Microsoft sign-in failed: unexpected token type")
    key = next((k for k in _jwks().get("keys", []) if k.get("kid") == header.get("kid")), None)
    if key is None:
        _JWKS_CACHE.clear()  # Microsoft rotates keys: fetch them again once
        key = next((k for k in _jwks().get("keys", []) if k.get("kid") == header.get("kid")), None)
    if key is None:
        raise Unauthorized("Microsoft sign-in failed: unknown signing key")
    public = rsa.RSAPublicNumbers(int.from_bytes(_b64url_decode(key["e"]), "big"),
                                  int.from_bytes(_b64url_decode(key["n"]), "big")).public_key()
    try:
        public.verify(signature, f"{head_b64}.{body_b64}".encode(), padding.PKCS1v15(), hashes.SHA256())
    except Exception as exc:  # noqa: BLE001 — any verification error means: do not trust it
        raise Unauthorized("Microsoft sign-in failed: the token signature is not valid") from exc
    now = time.time()
    expected_iss = f"{AUTHORITY}/{c['ENTRA_TENANT_ID']}/v2.0"
    problems = [
        claims.get("iss") != expected_iss and "issuer",
        claims.get("aud") != c["ENTRA_CLIENT_ID"] and "audience",
        not (isinstance(claims.get("exp"), (int, float)) and claims["exp"] > now - 60) and "expired",
        isinstance(claims.get("nbf"), (int, float)) and claims["nbf"] > now + 60 and "not yet valid",
        claims.get("nonce") != nonce and "nonce",
    ]
    if bad := [p for p in problems if p]:
        raise Unauthorized(f"Microsoft sign-in failed: {', '.join(bad)} check")
    return claims


def complete(args) -> tuple[User, str]:
    """Handle the callback: check state, exchange the code, verify the token, find the account."""
    flow = session.pop(SESSION_KEY, None)
    if args.get("error"):
        raise Unauthorized(f"Microsoft sign-in was cancelled or refused ({args.get('error')})")
    if not flow or not secrets.compare_digest(str(args.get("state") or ""), flow["state"]) \
            or time.time() - flow.get("at", 0) > 600:
        raise Unauthorized("Microsoft sign-in expired. Please try again.")
    tokens = _post_token(args.get("code") or "", flow["verifier"])
    if "id_token" not in tokens:
        raise Unauthorized("Microsoft sign-in failed: no identity returned")
    claims = verify_id_token(tokens["id_token"], flow["nonce"])
    user = link_account(claims)
    return user, flow["next"]


def link_account(claims: dict) -> User:
    oid = claims.get("oid")
    email = (claims.get("email") or claims.get("preferred_username") or "").strip().lower()
    user = db.session.scalar(select(User).where(User.entra_oid == oid, User.is_deleted.is_(False))) if oid else None
    if user is None and email:
        user = db.session.scalar(select(User).where(func.lower(User.email) == email, User.is_deleted.is_(False)))
        if user is not None and user.entra_oid and user.entra_oid != oid:
            user = None  # linked to a different Microsoft account
    if user is None or not user.is_active:
        raise Unauthorized("There is no active Control Tower account for this Microsoft account. Ask an administrator.")
    from app.core.audit import record_event

    first = user.entra_oid is None
    user.entra_oid = oid or user.entra_oid
    user.last_login_at = utcnow()
    user.failed_logins, user.locked_until = 0, None
    record_event(tenant_id=user.tenant_id, actor=user, entity_type="person", entity_id=user.id, operation="login",
                 reason="Microsoft Entra ID" + (" (account linked)" if first else ""), source="integration")
    db.session.commit()
    return user
