"""
Servidor Web - Logistica de Puertos y Aduanas RD
Acceso protegido con contraseña de administrador
"""

import subprocess
import os
import re
import hashlib
import secrets
import json
import uuid
import time
import bcrypt
from decimal import Decimal, InvalidOperation
from collections import defaultdict
from datetime import datetime, timedelta
from functools import wraps
from flask import Flask, request, jsonify, render_template, session, redirect, url_for, Response, make_response, send_from_directory

app = Flask(__name__, static_folder='static')

import sys
from pathlib import Path

# ── Fix encoding: piped stdout en Railway usa ASCII por defecto, causando
# UnicodeEncodeError cuando se imprime emoji en respuestas de Gemini ──────
try:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

# ── URL pública centralizada (CAMBIAR AQUÍ si cambia el dominio Railway) ──
_RAILWAY_PUBLIC_URL = "https://biblioteca-dga-production.up.railway.app"

# ── Rutas adaptables: local (Windows) o nube (Linux/Railway) ─────────────
_IS_CLOUD = os.environ.get("RAILWAY_ENVIRONMENT") or os.environ.get("RENDER") or (sys.platform != "win32")

if _IS_CLOUD:
    _BASE     = Path("/app")
    PYTHON    = sys.executable
    SKILL_DIR = str(_BASE / "notebooklm_skill")
    _DATA_DIR = _BASE / "data"
else:
    _BASE     = Path(r"C:\Users\Usuario")
    PYTHON    = str(_BASE / r".claude\skills\notebooklm\.venv\Scripts\python.exe")
    SKILL_DIR = str(_BASE / r".claude\skills\notebooklm")
    _DATA_DIR = Path(r"C:\Users\Usuario\Desktop\Biblioteca Notebooklm DGA\usuarios_y_administradores")

_DATA_DIR.mkdir(parents=True, exist_ok=True)

# ── SECRET_KEY segura: env var > archivo persistente > generada ─────────
def _get_or_create_secret_key():
    env_key = os.environ.get("SECRET_KEY")
    if env_key:
        return env_key
    key_file = _DATA_DIR / ".flask_secret_key"
    try:
        if key_file.exists():
            return key_file.read_text().strip()
    except Exception:
        pass
    key = secrets.token_hex(32)
    try:
        key_file.write_text(key)
    except Exception:
        pass
    return key

app.secret_key = _get_or_create_secret_key()

# ── Configuración de sesiones y cookies ─────────────────────────────────
app.permanent_session_lifetime          = timedelta(days=30)
app.config['SESSION_COOKIE_SAMESITE']   = 'Lax'
app.config['SESSION_COOKIE_HTTPONLY']    = True
app.config['SESSION_COOKIE_SECURE']     = bool(_IS_CLOUD)
app.config['MAX_CONTENT_LENGTH']        = 5 * 1024 * 1024  # 5 MB máx para uploads

# ── Nonce CSP por request ───────────────────────────────────────────────
from flask import g as _flask_g

@app.before_request
def _generate_csp_nonce():
    _flask_g.csp_nonce = secrets.token_urlsafe(16)

@app.context_processor
def _inject_csp_nonce():
    return {"csp_nonce": getattr(_flask_g, "csp_nonce", "")}

# ── Cabeceras de seguridad HTTP ─────────────────────────────────────────
@app.after_request
def _security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['Permissions-Policy'] = 'camera=(self), microphone=(), geolocation=()'
    if _IS_CLOUD:
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    nonce = getattr(_flask_g, "csp_nonce", "")
    csp = (
        "default-src 'self'; "
        f"script-src 'self' 'nonce-{nonce}' https://cdnjs.cloudflare.com; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "connect-src 'self'; "
        "frame-ancestors 'none';"
    )
    response.headers['Content-Security-Policy'] = csp
    return response

# ── Validación de uploads: extensión + magic bytes ──────────────────────
_ALLOWED_CONSULTAR = {".pdf", ".jpg", ".jpeg", ".png", ".webp", ".heic"}
_ALLOWED_AUDIO     = {".mp3", ".mp4", ".wav", ".webm", ".m4a", ".ogg", ".flac"}
_MAGIC_BYTES = {
    b"\x25\x50\x44\x46": "pdf",
    b"\xff\xd8\xff":      "jpeg",
    b"\x89\x50\x4e\x47": "png",
    b"\x52\x49\x46\x46": "webp",
}

def _validar_upload(file_obj, allowed_exts):
    """Valida extensión y magic bytes. Devuelve (ok: bool, error: str)."""
    filename = file_obj.filename or ""
    ext = os.path.splitext(filename)[1].lower()
    if ext not in allowed_exts:
        return False, f"Tipo no permitido. Usa: {', '.join(sorted(allowed_exts))}"
    header = file_obj.stream.read(12)
    file_obj.stream.seek(0)
    if len(header) < 4:
        return False, "Archivo vacío o corrupto."
    for magic in _MAGIC_BYTES:
        if header[:len(magic)] == magic:
            return True, ""
    if ext in {".heic"}:
        return True, ""
    if ext in {".jpg", ".jpeg"} and header[:3] != b"\xff\xd8\xff":
        return False, "El archivo no es una imagen JPEG válida."
    if ext == ".pdf" and header[:4] != b"\x25\x50\x44\x46":
        return False, "El archivo no es un PDF válido."
    if ext == ".webp" and (len(header) < 12 or header[8:12] != b"WEBP"):
        return False, "El archivo no es un WebP válido."
    return True, ""

# ── Cache de consultas frecuentes ──────────────────────────────────────────
_CACHE_CONSULTAS_PATH = Path(__file__).parent / "notebooklm_skill" / "data" / "fuentes_nomenclatura" / "consultas_cache.json"
_CACHE_CONSULTAS: dict = {}
_CACHE_CONSULTAS_TTL  = 7 * 24 * 3600  # 7 días
_CACHE_CONSULTAS_MAX  = 500

def _cargar_cache_consultas():
    global _CACHE_CONSULTAS
    try:
        if _CACHE_CONSULTAS_PATH.exists():
            _CACHE_CONSULTAS = json.loads(_CACHE_CONSULTAS_PATH.read_text(encoding="utf-8"))
    except Exception:
        _CACHE_CONSULTAS = {}

def _guardar_cache_consultas():
    try:
        _CACHE_CONSULTAS_PATH.write_text(
            json.dumps(_CACHE_CONSULTAS, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception:
        pass

def _cache_key(question: str, notebook_id: str) -> str:
    return hashlib.md5((question.lower().strip() + "|" + notebook_id).encode()).hexdigest()

def _get_cached(question: str, notebook_id: str):
    entry = _CACHE_CONSULTAS.get(_cache_key(question, notebook_id))
    if not entry:
        return None
    if time.time() - entry.get("ts", 0) > _CACHE_CONSULTAS_TTL:
        del _CACHE_CONSULTAS[_cache_key(question, notebook_id)]
        return None
    entry["hits"] = entry.get("hits", 0) + 1
    return entry["answer"]

def _set_cached(question: str, notebook_id: str, answer: str):
    if len(_CACHE_CONSULTAS) >= _CACHE_CONSULTAS_MAX:
        oldest = min(_CACHE_CONSULTAS, key=lambda k: _CACHE_CONSULTAS[k].get("ts", 0))
        del _CACHE_CONSULTAS[oldest]
    _CACHE_CONSULTAS[_cache_key(question, notebook_id)] = {"answer": answer, "ts": time.time(), "hits": 0}
    _guardar_cache_consultas()

_cargar_cache_consultas()

# ── Rate limiter en memoria ─────────────────────────────────────────────
_rate_limits = defaultdict(list)
_RATE_CONFIGS = {
    'login':           {'max': 5,  'window': 900},   # 5 intentos / 15 min
    'recovery':        {'max': 3,  'window': 600},   # 3 solicitudes / 10 min
    'recovery_verify': {'max': 5,  'window': 300},   # 5 verificaciones / 5 min
    'password_change': {'max': 5,  'window': 600},   # 5 cambios / 10 min
    'registro':        {'max': 5,  'window': 600},   # 5 registros / 10 min
    'consulta':        {'max': 20, 'window': 60},    # 20 consultas / min
}

def _rate_limited(key, action='login'):
    cfg = _RATE_CONFIGS.get(action, {'max': 10, 'window': 600})
    now = time.time()
    _rate_limits[key] = [t for t in _rate_limits[key] if now - t < cfg['window']]
    if len(_rate_limits[key]) >= cfg['max']:
        return True
    _rate_limits[key].append(now)
    return False

def _get_client_ip():
    return request.headers.get('X-Forwarded-For', request.remote_addr or '127.0.0.1').split(',')[0].strip()

# ── Contraseñas por defecto (hash SHA-256 legacy, se rehashean a bcrypt
# en el primer login exitoso). Mantener hex asegura compat con passwords.json
# existentes en producción. ─────────────────────────────────────────────
_DEFAULT_MASTER_HASH = hashlib.sha256(b"DGA2024*").hexdigest()
_DEFAULT_GUEST_HASH  = hashlib.sha256(b"Puertos2024").hexdigest()

# ── Password hashing (bcrypt con pre-hash SHA-256 para sortear el límite
# de 72 bytes y evitar truncamiento silencioso). Verifica ambos formatos:
# legacy (SHA-256 hex de 64 chars) y bcrypt. Devuelve needs_rehash=True
# cuando el hash almacenado es legacy, para migración perezosa. ────────
_BCRYPT_ROUNDS = 12  # ~250ms por verificación en hardware moderno

def _pw_hash(pw: str) -> str:
    digest = hashlib.sha256(pw.encode("utf-8")).digest()
    return bcrypt.hashpw(digest, bcrypt.gensalt(rounds=_BCRYPT_ROUNDS)).decode("ascii")

def _pw_verify(pw: str, stored: str):
    """Devuelve (ok: bool, needs_rehash: bool). Soporta legacy SHA-256 hex + bcrypt."""
    if not pw or not stored:
        return (False, False)
    # Legacy SHA-256 hex (64 chars hex)
    if len(stored) == 64 and all(c in "0123456789abcdefABCDEF" for c in stored):
        legacy = hashlib.sha256(pw.encode("utf-8")).hexdigest()
        return (secrets.compare_digest(legacy, stored.lower()), True)
    # Bcrypt ($2a$ / $2b$ / $2y$)
    try:
        digest = hashlib.sha256(pw.encode("utf-8")).digest()
        return (bcrypt.checkpw(digest, stored.encode("ascii")), False)
    except Exception:
        return (False, False)

# ── Validación SON DGA (8 dígitos estándar con apertura nacional opcional) ─
_SON_RE = re.compile(r"^\d{4}\.\d{2}\.\d{2}(\.\d{2})?$")

def _validar_son(codigo: str) -> bool:
    return bool(codigo and _SON_RE.match(codigo.strip()))

# ── Parseo de gravamen con Decimal (evita errores de coma flotante en
# tasas como 18.5%). Acepta "18", "18.5", "18,5". Devuelve None si inválido. ─
def _parse_gravamen(valor: str):
    if valor is None:
        return None
    s = str(valor).strip().replace("%", "").replace(",", ".")
    if not s:
        return None
    try:
        d = Decimal(s)
    except InvalidOperation:
        return None
    if d < 0 or d > 100:
        return None
    return d

USERS_FILE       = str(_DATA_DIR / "usuarios.json")
SOLICITUDES_FILE = str(_DATA_DIR / "solicitudes.json")
PASSWORDS_FILE   = str(_DATA_DIR / "passwords.json")
HISTORIAL_FILE   = str(_DATA_DIR / "historial_invitados.json")
RECOVERY_FILE    = str(_DATA_DIR / "recuperaciones.json")
CUADERNOS_FILE   = str(_DATA_DIR / "cuadernos.json")

# ── Notificación WhatsApp al admin (CallMeBot API) ────────────────────────
_ADMIN_WHATSAPP = "18093547636"  # (809)354-7636 con código país +1 RD

def _notificar_whatsapp_registro(nombre, correo, whatsapp_usuario):
    """Envía WhatsApp al admin cuando alguien se registra. No bloquea si falla."""
    apikey = os.environ.get("CALLMEBOT_APIKEY", "")
    if not apikey:
        print(f"[WA_NOTIFY] Sin CALLMEBOT_APIKEY — registro de {correo} no notificado por WhatsApp")
        return False
    try:
        import urllib.request
        import urllib.parse
        mensaje = (
            f"📲 Nuevo registro en Biblioteca DGA\n\n"
            f"Nombre: {nombre}\n"
            f"Correo: {correo}\n"
            f"WhatsApp: {whatsapp_usuario}\n"
            f"Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        )
        url = (
            f"https://api.callmebot.com/whatsapp.php"
            f"?phone={_ADMIN_WHATSAPP}"
            f"&text={urllib.parse.quote(mensaje)}"
            f"&apikey={apikey}"
        )
        req = urllib.request.Request(url, method='GET')
        with urllib.request.urlopen(req, timeout=10) as resp:
            status = resp.status
            print(f"[WA_NOTIFY] Enviado a {_ADMIN_WHATSAPP} — status={status}")
            return status == 200
    except Exception as e:
        print(f"[WA_NOTIFY] Error enviando WhatsApp: {e}")
        return False

# ── Helpers de historial (solo admin puede ver/gestionar) ────────────────
def load_historial():
    try:
        with open(HISTORIAL_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"registros": []}

def save_historial(data):
    with open(HISTORIAL_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_recovery():
    try:
        with open(RECOVERY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"solicitudes": []}

def save_recovery(data):
    with open(RECOVERY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def log_historial(correo, nombre, evento, detalle=""):
    data = load_historial()
    data["registros"].append({
        "id":      str(uuid.uuid4()),
        "correo":  correo,
        "nombre":  nombre,
        "evento":  evento,
        "detalle": detalle,
        "fecha":   datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })
    save_historial(data)

# ── Helpers de contraseñas ───────────────────────────────────────────────
def load_passwords():
    try:
        with open(PASSWORDS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return {"master": _DEFAULT_MASTER_HASH, "invitado": _DEFAULT_GUEST_HASH}
    # ── Migración: renombrar "admin" → "master" ──
    if "admin" in data and "master" not in data:
        data["master"] = data.pop("admin")
        save_passwords(data)
    return data

def save_passwords(data):
    with open(PASSWORDS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_master_hash():
    return load_passwords().get("master", _DEFAULT_MASTER_HASH)

def get_guest_hash():
    return load_passwords().get("invitado", _DEFAULT_GUEST_HASH)

# ── Correos oficiales del sistema ────────────────────────────────────────
DISTRIBUTION_EMAIL = "consultoria.puertos.aduanas@gmail.com"   # envia la app
SUPPORT_EMAIL      = "consulta.puertos.aduanas@gmail.com"      # recibe solicitudes
WHATSAPP_ADMIN     = "18093547636"                              # WhatsApp admin

# ── Cuadernos dinámicos ──────────────────────────────────────────────────
_DEFAULT_NOTEBOOKS = [
    {"id": "biblioteca-de-nomenclaturas",                        "nombre": "Nomenclaturas",          "emoji": "📋"},
    {"id": "biblioteca-legal-y-procedimiento-dga",               "nombre": "Legal y Procedimientos", "emoji": "⚖️"},
    {"id": "biblioteca-para-valoracion-dga",                     "nombre": "Valoracion",             "emoji": "💰"},
    {"id": "biblioteca-guia-integral-de-regimenes-y-subastas",   "nombre": "Regimenes y Subastas",   "emoji": "📦"},
    {"id": "biblioteca-para-aforo-dga",                          "nombre": "Aforo DGA",              "emoji": "🔍"},
    {"id": "biblioteca-procedimiento-vucerd",                    "nombre": "VUCERD",                 "emoji": "🪟"},
    {"id": "biblioteca-de-normas-y-origen-dga",                  "nombre": "Normas y Origen",        "emoji": "🌐"},
    {"id": "guia-maestra-comercio-exterior",                     "nombre": "Guía Maestra Comercio",  "emoji": "📖"},
]

def load_cuadernos():
    try:
        with open(CUADERNOS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("cuadernos", _DEFAULT_NOTEBOOKS)
    except Exception:
        return _DEFAULT_NOTEBOOKS

def save_cuadernos(lista):
    with open(CUADERNOS_FILE, "w", encoding="utf-8") as f:
        json.dump({"cuadernos": lista}, f, ensure_ascii=False, indent=2)

def get_notebooks():
    return load_cuadernos()

# ── Helpers de usuarios ──────────────────────────────────────────────────
def load_users():
    try:
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"usuarios": []}

def save_users(data):
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def find_user_by_email(email):
    data = load_users()
    for u in data["usuarios"]:
        if u["correo"].lower() == email.lower():
            return u
    return None

def find_user_by_id(uid):
    for u in load_users().get("usuarios", []):
        if u["id"] == uid:
            return u
    return None

# ── Decorador de protección ─────────────────────────────────────────────
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    """Legado — redirige a admin_or_master_required."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in") or session.get("role") not in ("master", "operativo"):
            return jsonify({"error": "Acceso denegado"}), 403
        return f(*args, **kwargs)
    return decorated

def master_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in") or session.get("role") != "master":
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

def admin_or_master_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in") or session.get("role") not in ("master", "operativo"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

# ── Guia de registro ───────────────────────────────────────────────────
@app.route("/guia-registro")
def guia_registro():
    return render_template("guia_registro.html")

# ── Registro ────────────────────────────────────────────────────────────
@app.route("/registro", methods=["GET", "POST"])
def registro():
    if request.method == "POST":
        ip = _get_client_ip()
        if _rate_limited(f"registro:{ip}", 'registro'):
            return render_template("registro.html", error="Demasiados intentos de registro. Espera 10 minutos.")

        d = request.form
        correo = d.get("correo", "").strip().lower()
        if not correo:
            return render_template("registro.html", error="El correo es obligatorio.")
        if find_user_by_email(correo):
            return render_template("registro.html", error="Este correo ya está registrado. Inicia sesión.")

        nuevo = {
            "id": str(uuid.uuid4()),
            "nombre":     d.get("nombre", "").strip(),
            "correo":     correo,
            "whatsapp":   d.get("whatsapp", "").strip(),
            "profesion":  d.get("profesion", "").strip(),
            "dedicacion": d.get("dedicacion", "").strip(),
            "pais":       d.get("pais", "República Dominicana").strip(),
            "provincia":  d.get("provincia", "").strip(),
            "municipio":  d.get("municipio", "").strip(),
            "calle":      d.get("calle", "").strip(),
            "numero":     d.get("numero", "").strip(),
            "fecha_registro":   datetime.now().strftime("%Y-%m-%d %H:%M"),
            "bloqueado":        False,
            "password_changed": False
        }
        data = load_users()
        data["usuarios"].append(nuevo)
        save_users(data)
        log_historial(correo, nuevo["nombre"], "registro", "Nuevo usuario registrado")

        # Notificar al admin por WhatsApp (no bloquea si falla)
        import threading
        threading.Thread(
            target=_notificar_whatsapp_registro,
            args=(nuevo["nombre"], correo, nuevo["whatsapp"]),
            daemon=True
        ).start()

        session.permanent               = True
        session["logged_in"]            = True
        session["role"]                 = "invitado"
        session["correo"]               = correo
        session["nombre"]               = nuevo["nombre"]
        session["must_change_password"] = True
        return redirect(url_for("index"))

    return render_template("registro.html", error=None)

# ── Login ───────────────────────────────────────────────────────────────
@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    # Detectar si el formulario viene desde /invitado para redirigir errores allí
    from_invitado = False
    if request.method == "POST":
        ip = _get_client_ip()
        if _rate_limited(f"login:{ip}", 'login'):
            error = "Demasiados intentos. Espera 15 minutos antes de intentar de nuevo."
            referer = request.headers.get("Referer", "")
            if "/invitado" in referer:
                return render_template("login_invitado.html", error=error)
            return render_template("login.html", error=error)

        pwd      = request.form.get("password", "")
        role_req = request.form.get("role", "admin")
        correo   = request.form.get("correo", "").strip().lower()
        referer  = request.headers.get("Referer", "")
        from_invitado = role_req == "invitado" and "/invitado" in referer

        # Backward compat: old forms send "admin" → treat as "master"
        if role_req == "admin":
            role_req = "master"

        master_stored = get_master_hash()
        ok_master, master_needs_rehash = _pw_verify(pwd, master_stored)
        if role_req == "master" and ok_master:
            if master_needs_rehash:
                try:
                    pwds = load_passwords()
                    pwds["master"] = _pw_hash(pwd)
                    save_passwords(pwds)
                except Exception as e:
                    print(f"[AUTH] Rehash master falló: {e}")
            if correo:
                # Master con correo → verificar si quiere entrar como operativo
                usuario = find_user_by_email(correo)
                if usuario and usuario.get("tipo") == "operativo" and not usuario.get("bloqueado"):
                    # Pero la contraseña master no sirve para operativo
                    error = "Para acceso operativo usa tu contraseña personal, no la maestra."
                elif usuario and usuario.get("bloqueado"):
                    error = "Tu acceso ha sido bloqueado por el administrador."
                elif usuario:
                    error = "Este correo no tiene permisos de administrador."
                else:
                    error = "Correo no encontrado. Ingresa sin correo para acceso maestro."
            else:
                session.permanent    = True
                session["logged_in"] = True
                session["role"]      = "master"
                session["correo"]    = "master"
                session["nombre"]    = "Administrador Master"
                log_historial("master", "Administrador Master", "inicio_sesion", "Acceso master")
                return redirect(url_for("index"))

        elif role_req == "operativo":
            if not correo:
                error = "Ingresa tu correo para acceder como operativo."
            else:
                usuario = find_user_by_email(correo)
                if not usuario:
                    error = "Correo no encontrado."
                elif usuario.get("tipo") != "operativo":
                    error = "Este correo no tiene permisos de operativo."
                elif usuario.get("bloqueado"):
                    error = "Tu acceso ha sido bloqueado por el administrador."
                else:
                    user_pw_hash = usuario.get("password_hash", "")
                    if not user_pw_hash:
                        error = "Tu cuenta operativa aún no tiene contraseña asignada. Contacta al administrador."
                    else:
                        ok_op, op_needs_rehash = _pw_verify(pwd, user_pw_hash)
                        if not ok_op:
                            error = "Contraseña incorrecta. Intenta de nuevo."
                        else:
                            if op_needs_rehash:
                                try:
                                    data = load_users()
                                    for u in data["usuarios"]:
                                        if u["correo"].lower() == correo.lower():
                                            u["password_hash"] = _pw_hash(pwd)
                                            break
                                    save_users(data)
                                except Exception as e:
                                    print(f"[AUTH] Rehash operativo falló: {e}")
                            primer_acceso_op = not usuario.get("password_changed", False)
                            session.permanent    = True
                            session["logged_in"] = True
                            session["role"]      = "operativo"
                            session["correo"]    = correo
                            session["nombre"]    = usuario["nombre"]
                            session["must_change_password"] = primer_acceso_op
                            if primer_acceso_op:
                                session["_first_access_pwd"] = pwd
                            evento_op = "primer_acceso" if primer_acceso_op else "inicio_sesion"
                            detalle_op = "Primer acceso operativo — debe cambiar contraseña" if primer_acceso_op else "Inicio de sesión operativo"
                            log_historial(correo, usuario["nombre"], evento_op, detalle_op)
                            return redirect(url_for("index"))

        elif role_req == "invitado":
            if not correo:
                error = "Ingresa tu correo registrado para acceder como invitado."
            else:
                usuario = find_user_by_email(correo)
                if not usuario:
                    error = "Correo no registrado. ¿Primera vez? Regístrate primero."
                elif usuario.get("bloqueado"):
                    error = "Tu acceso ha sido bloqueado por el administrador."
                else:
                    primer_acceso = not usuario.get("password_changed", False)
                    user_pw_hash  = usuario.get("password_hash", "")
                    guest_stored  = get_guest_hash()

                    ok_personal   = False
                    personal_rehash = False
                    if user_pw_hash:
                        ok_personal, personal_rehash = _pw_verify(pwd, user_pw_hash)

                    ok_shared    = False
                    shared_rehash = False
                    if not user_pw_hash or primer_acceso:
                        ok_shared, shared_rehash = _pw_verify(pwd, guest_stored)

                    pwd_ok = ok_personal or ok_shared
                    if not pwd_ok:
                        error = "Contraseña incorrecta. Intenta de nuevo."
                    else:
                        # Migración perezosa del hash que validó
                        try:
                            if ok_personal and personal_rehash:
                                data_u = load_users()
                                for u in data_u["usuarios"]:
                                    if u["correo"].lower() == correo.lower():
                                        u["password_hash"] = _pw_hash(pwd)
                                        break
                                save_users(data_u)
                            elif ok_shared and shared_rehash:
                                pwds = load_passwords()
                                pwds["invitado"] = _pw_hash(pwd)
                                save_passwords(pwds)
                        except Exception as e:
                            print(f"[AUTH] Rehash invitado falló: {e}")
                        session.permanent             = True
                        session["logged_in"]          = True
                        session["role"]               = "invitado"
                        session["correo"]             = correo
                        session["nombre"]             = usuario["nombre"]
                        session["must_change_password"] = primer_acceso
                        if primer_acceso:
                            session["_first_access_pwd"] = pwd
                        evento = "primer_acceso" if primer_acceso else "inicio_sesion"
                        log_historial(correo, usuario["nombre"], evento,
                                      "Primer acceso — debe cambiar contraseña" if primer_acceso else "Inicio de sesión")
                        return redirect(url_for("index"))
        else:
            error = "Contraseña incorrecta. Intenta de nuevo."

    # Si el formulario vino de /invitado, devolver errores allí
    if from_invitado and error:
        return render_template("login_invitado.html", error=error)
    return render_template("login.html", error=error)

@app.route("/invitado", methods=["GET"])
def login_invitado():
    """Interfaz de login exclusiva para usuarios/invitados (sin opción admin)."""
    if session.get("logged_in"):
        return redirect(url_for("index"))
    return render_template("login_invitado.html", error=None)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# ── App principal (protegida) ────────────────────────────────────────────
@app.route("/")
@login_required
def index():
    role                 = session.get("role", "invitado")
    nombre               = session.get("nombre", "")
    correo               = session.get("correo", "")
    must_change_password = session.get("must_change_password", False)
    first_access_pwd     = session.get("_first_access_pwd", "") if must_change_password else ""
    return render_template("index.html", notebooks=get_notebooks(), role=role, nombre=nombre,
                           correo=correo, must_change_password=must_change_password,
                           first_access_pwd=first_access_pwd,
                           public_url=_get_public_url())

@app.route("/consultar", methods=["POST"])
@login_required
def consultar():
    # Soporta JSON (sin archivo) y multipart/form-data (con archivo)
    if request.content_type and request.content_type.startswith("multipart/form-data"):
        question    = request.form.get("question", "").strip()
        notebook_id = request.form.get("notebook_id", "")
        archivo     = request.files.get("archivo")
    else:
        data        = request.json or {}
        question    = data.get("question", "").strip()
        notebook_id = data.get("notebook_id", "")
        archivo     = None

    if not question and not archivo:
        return jsonify({"error": "Escribe una pregunta o adjunta una foto del producto"}), 400
    if not notebook_id:
        return jsonify({"error": "Selecciona un cuaderno"}), 400

    # ── Validación de notebook_id contra lista conocida ──
    valid_ids = [nb['id'] for nb in get_notebooks()]
    if notebook_id not in valid_ids:
        return jsonify({"error": "Cuaderno no válido."}), 400

    # ── Rate limit por IP ──
    ip = _get_client_ip()
    if _rate_limited(f"consulta:{ip}", 'consulta'):
        return jsonify({"error": "Demasiadas consultas. Espera un momento."}), 429

    # ── Cache hit: respuesta instantánea para consultas repetidas (solo texto) ──
    if not archivo:
        cached = _get_cached(question, notebook_id)
        if cached:
            print(f"[CACHE_HIT] '{question[:60]}' — devuelto sin llamar a Gemini")
            return jsonify({"answer": cached, "from_cache": True})

    # ── Sub-agente merceológico: cache-first con fichas previas ──
    # Si hay ficha merceológica del producto, respuesta en <500ms sin llamar a Gemini.
    # Solo para texto (no imágenes) y cuaderno de nomenclaturas.
    if not archivo:
        try:
            import sys as _sys
            _ag_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                     "notebooklm_skill", "scripts")
            if _ag_path not in _sys.path:
                _sys.path.insert(0, _ag_path)
            from merceologia_agent import intentar_respuesta_cache
            hit = intentar_respuesta_cache(question, notebook_id, umbral=0.5)
            if hit:
                respuesta_cache, meta_cache = hit
                print(f"[MERCEOLOGIA_HIT] slug={meta_cache['slug']} "
                      f"codigo={meta_cache['codigo']} score={meta_cache['score']} "
                      f"tiempo={meta_cache['elapsed_ms']}ms")
                # Guardar en cache general de consultas
                _set_cached(question, notebook_id, respuesta_cache)
                return jsonify({
                    "answer": respuesta_cache,
                    "from_cache": True,
                    "cache_via": "merceologia_agent",
                    "meta": meta_cache,
                })
        except Exception as _e:
            print(f"[MERCEOLOGIA_AGENT] Error no critico: {_e}")
            # Continuar con flujo normal (Gemini)

    # Si hay archivo adjunto, extraer texto / analizar imagen y añadirlo a la pregunta
    producto_identificado = ""
    if archivo:
        ok_up, err_up = _validar_upload(archivo, _ALLOWED_CONSULTAR)
        if not ok_up:
            return jsonify({"error": err_up}), 400
        try:
            import tempfile, os as _os
            ext = _os.path.splitext(archivo.filename or "")[1].lower()
            with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
                archivo.save(tmp.name)
                tmp_path = tmp.name
            texto_archivo = _extraer_texto_archivo(tmp_path, ext)
            _os.unlink(tmp_path)
            if texto_archivo:
                # Extraer nombre del producto de la respuesta de Gemini Vision
                import re as _re
                _m = _re.search(r"PRODUCTO:\s*(.+)", texto_archivo)
                if _m:
                    producto_identificado = _m.group(1).strip()
                if not question:
                    # Solo foto, sin texto: ejecutar protocolo merceologico completo
                    question = (
                        "INSTRUCCION OBLIGATORIA: El usuario envio una imagen de un producto. "
                        "Gemini Vision ya lo identifico. DEBES clasificarlo arancelariamente "
                        "aplicando el PROTOCOLO DE INVESTIGACION MERCEOLOGICA completo (8 fases). "
                        "NUNCA pidas mas informacion al usuario. NUNCA digas que necesitas descripcion. "
                        "Trabaja con la identificacion proporcionada:\n\n"
                        + texto_archivo[:3000]
                    )
                    print(f"[CONSULTAR] Consulta imagen+protocolo: {question[:120]}")
                else:
                    question = (
                        question + "\n\n[Producto identificado desde imagen adjunta — "
                        "clasificar obligatoriamente, NO pedir mas info]:\n"
                        + texto_archivo[:3000]
                    )
        except Exception as ex:
            print(f"[CONSULTAR] Error procesando archivo: {ex}")
            if not question:
                return jsonify({"error": "No se pudo analizar la imagen. Intenta con otra foto o escribe tu consulta."}), 400

    # Timeout por tipo de consulta:
    #   Texto: 60s (Gemini + Arancel PDF + supervisor)
    #   Imagen: 90s (Vision API + Gemini + Arancel PDF + supervisor)
    tiene_imagen = bool(producto_identificado) or (archivo is not None)
    timeout_consulta = 90 if tiene_imagen else 60

    try:
        answer = ask_notebooklm(question, notebook_id, timeout=timeout_consulta)
        # Guardar en cache solo consultas de texto (no imágenes, no errores)
        if not archivo and answer and not answer.startswith("[ERROR"):
            _set_cached(question, notebook_id, answer)
        resp = {"answer": answer}
        if producto_identificado:
            resp["producto_identificado"] = producto_identificado
        return jsonify(resp)
    except subprocess.TimeoutExpired:
        return jsonify({"error": "Tiempo de espera agotado. Intenta de nuevo."}), 504
    except Exception as e:
        import traceback as _tb
        print(f"[CONSULTAR_ERROR] {type(e).__name__}: {e}")
        print(f"[CONSULTAR_TRACEBACK]\n{_tb.format_exc()}")
        return jsonify({"error": "Error interno al procesar la consulta. Intente de nuevo."}), 500


def _extraer_texto_archivo(path, ext):
    """Extrae texto de PDF o imagen para incluir en la consulta."""
    try:
        if ext == ".pdf":
            try:
                import pdfplumber
                with pdfplumber.open(path) as pdf:
                    return "\n".join(p.extract_text() or "" for p in pdf.pages[:5]).strip()
            except ImportError:
                pass
            try:
                import PyPDF2
                with open(path, "rb") as f:
                    reader = PyPDF2.PdfReader(f)
                    return "\n".join(page.extract_text() or "" for page in reader.pages[:5]).strip()
            except ImportError:
                pass
            return "[PDF adjunto — no se pudo extraer texto]"
        elif ext in (".jpg", ".jpeg", ".png", ".heic", ".webp"):
            # Usar Gemini Vision para analizar la imagen
            desc = _identificar_producto_imagen(path)
            if desc:
                return desc
            return "[Imagen adjunta — producto no identificado]"
    except Exception as e:
        return f"[Error al leer archivo: {e}]"
    return ""


def _comprimir_imagen(image_path, max_size_kb=500, max_dim=1024):
    """Comprime imagen automáticamente para acelerar upload a Gemini Vision.
    Reduce a max 1024px y JPEG calidad 80. Retorna path del archivo comprimido."""
    try:
        from PIL import Image
        size_kb = os.path.getsize(image_path) / 1024
        if size_kb <= max_size_kb:
            print(f"[VISION] Imagen ya es pequeña ({size_kb:.0f}KB) — sin comprimir")
            return image_path

        img = Image.open(image_path)
        # Convertir RGBA/P a RGB para JPEG
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        # Redimensionar si excede max_dim
        w, h = img.size
        if max(w, h) > max_dim:
            ratio = max_dim / max(w, h)
            img = img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)
        # Guardar como JPEG comprimido
        import tempfile
        compressed = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
        img.save(compressed.name, "JPEG", quality=80, optimize=True)
        new_size = os.path.getsize(compressed.name) / 1024
        print(f"[VISION] Imagen comprimida: {size_kb:.0f}KB → {new_size:.0f}KB "
              f"({img.size[0]}x{img.size[1]})")
        return compressed.name
    except Exception as e:
        print(f"[VISION] Error comprimiendo imagen ({e}) — usando original")
        return image_path


def _identificar_producto_imagen(image_path):
    """Usa Gemini Vision para identificar un producto desde una foto.
    Devuelve una descripción merceológica del producto para clasificación."""
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        return None
    compressed_path = None
    try:
        from google import genai as _genai_v
        from google.genai import types as _types_v
        _client = _genai_v.Client(api_key=api_key)

        # Comprimir imagen automáticamente (2MB → ~200KB, acelera upload)
        compressed_path = _comprimir_imagen(image_path)
        upload_path = compressed_path

        # Subir imagen a Gemini File API
        print(f"[VISION] Subiendo imagen para análisis: {upload_path}")
        img_file = _client.files.upload(file=upload_path)
        # Esperar a que esté activa
        for _ in range(10):
            status = _client.files.get(name=img_file.name)
            if status.state == "ACTIVE":
                break
            time.sleep(1)

        _vision_config = _types_v.GenerateContentConfig(max_output_tokens=1024)
        prompt = (
            "INSTRUCCION OBLIGATORIA: Eres un perito merceólogo aduanero. "
            "Tu UNICA tarea es identificar el PRODUCTO FISICO visible en la imagen.\n\n"
            "REGLAS ESTRICTAS:\n"
            "1. SIEMPRE identifica el producto. NUNCA digas que no puedes identificarlo.\n"
            "2. NUNCA pidas mas informacion al usuario. Trabaja con lo que ves.\n"
            "3. Si la imagen muestra un documento, libro, etiqueta o empaque, "
            "ignora el texto/titulo y enfocate en el OBJETO FISICO visible.\n"
            "4. Si solo ves un documento/libro, identifica ESE objeto (ej: 'libro impreso').\n"
            "5. Describe lo que VES, no lo que lees en la imagen.\n\n"
            "PROTOCOLO MERCEOLOGICO — responde EXACTAMENTE asi:\n"
            "PRODUCTO: [nombre tecnico del objeto fisico visible]\n"
            "MATERIAL: [material constitutivo principal que se observa]\n"
            "FUNCION: [funcion tecnica o uso del producto]\n"
            "ESTADO: [Producto Acabado / Accesorio / Componente / Materia Prima]\n"
            "DESCRIPCION: [descripcion tecnica de 2-3 lineas: naturaleza, "
            "estado fisico, acabado superficial, presentacion comercial]\n\n"
            "EJEMPLO para un tornillo:\n"
            "PRODUCTO: Tornillo autorroscante de cabeza hexagonal\n"
            "MATERIAL: Acero al carbono con recubrimiento galvanizado\n"
            "FUNCION: Elemento de fijacion mecanica para union de piezas\n"
            "ESTADO: Producto Acabado\n"
            "DESCRIPCION: Tornillo metalico de acero galvanizado, cabeza hexagonal, "
            "rosca autorroscante, estado solido, acabado brillante, presentacion unitaria."
        )
        print(f"[VISION] Enviando imagen a Gemini Vision...")
        response = _client.models.generate_content(
            model="gemini-2.0-flash",
            contents=[img_file, prompt],
            config=_vision_config
        )
        desc = response.text.strip()
        print(f"[VISION] Producto identificado: {desc[:150]}")

        # Validar que Vision no pidio mas info ni se nego a identificar
        _rechazos = ["no puedo identificar", "necesito que", "proporcione",
                     "describa el producto", "no me permite identificar",
                     "no es posible determinar"]
        if any(r in desc.lower() for r in _rechazos):
            print("[VISION] Vision intento rechazar — forzando re-identificacion")
            response2 = _client.models.generate_content(
                model="gemini-2.0-flash",
                contents=[img_file, "Describe el objeto fisico visible en esta imagen. "
                 "Responde: PRODUCTO: [que es] MATERIAL: [de que esta hecho] "
                 "FUNCION: [para que sirve] DESCRIPCION: [descripcion tecnica breve]"],
                config=_vision_config
            )
            desc = response2.text.strip()
            print(f"[VISION] Re-identificacion: {desc[:150]}")

        # Limpiar archivo subido en Gemini
        try:
            _client.files.delete(name=img_file.name)
        except Exception:
            pass

        # Limpiar archivo comprimido temporal
        if compressed_path and compressed_path != image_path:
            try:
                os.unlink(compressed_path)
            except Exception:
                pass

        return desc
    except Exception as e:
        print(f"[VISION] Error analizando imagen: {e}")
        # Limpiar archivo comprimido temporal en caso de error
        if compressed_path and compressed_path != image_path:
            try:
                os.unlink(compressed_path)
            except Exception:
                pass
        return None

@app.route("/estado")
@login_required
def estado():
    cmd = [PYTHON, "scripts/auth_manager.py", "status"]
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    result = subprocess.run(cmd, cwd=SKILL_DIR, capture_output=True, text=True, encoding="utf-8", env=env)
    return jsonify({"status": result.stdout.strip()})

# ── Solicitudes de instalador ────────────────────────────────────────────
def load_solicitudes():
    try:
        with open(SOLICITUDES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"solicitudes": []}

def save_solicitudes(data):
    with open(SOLICITUDES_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

@app.route("/solicitar-app", methods=["POST"])
@login_required
def solicitar_app():
    correo = session.get("correo", "")
    nombre = session.get("nombre", "")
    if not correo or correo in ("admin", "master"):
        return jsonify({"error": "Solo los invitados pueden solicitar el instalador."}), 400

    data = load_solicitudes()
    # Evitar solicitudes duplicadas pendientes
    pendientes = [s for s in data["solicitudes"] if s["correo"] == correo and s["estado"] == "pendiente"]
    if pendientes:
        return jsonify({"ok": True, "mensaje": "Ya tienes una solicitud pendiente. El administrador te contactará pronto."})

    data["solicitudes"].append({
        "id":     str(uuid.uuid4()),
        "nombre": nombre,
        "correo": correo,
        "fecha":  datetime.now().strftime("%Y-%m-%d %H:%M"),
        "estado": "pendiente"
    })
    save_solicitudes(data)
    return jsonify({"ok": True, "mensaje": f"¡Solicitud registrada! El administrador enviará el instalador a {correo}."})

@app.route("/admin/solicitudes")
@admin_or_master_required
def admin_solicitudes():
    return jsonify(load_solicitudes())

@app.route("/admin/solicitudes/marcar", methods=["POST"])
@admin_or_master_required
def admin_marcar_solicitud():
    sid    = request.json.get("id", "")
    estado = request.json.get("estado", "enviado")
    data   = load_solicitudes()
    for s in data["solicitudes"]:
        if s["id"] == sid:
            s["estado"] = estado
            save_solicitudes(data)
            return jsonify({"ok": True})
    return jsonify({"error": "Solicitud no encontrada"}), 404

# ── Admin: gestión de usuarios ───────────────────────────────────────────
@app.route("/admin/usuarios")
@admin_or_master_required
def admin_usuarios():
    data = load_users()
    # Operativo no ve a otros operativos
    if session.get("role") == "operativo":
        data = dict(data)
        data["usuarios"] = [u for u in data["usuarios"] if u.get("tipo") != "operativo"]
    return jsonify(data)

@app.route("/admin/bloquear", methods=["POST"])
@admin_or_master_required
def admin_bloquear():
    uid    = request.json.get("id", "")
    estado = request.json.get("bloqueado", True)
    # Operativo no puede bloquear a otro operativo
    if session.get("role") == "operativo":
        target = find_user_by_id(uid)
        if target and target.get("tipo") == "operativo":
            return jsonify({"error": "No tienes permiso para bloquear a un operativo."}), 403
    data = load_users()
    for u in data["usuarios"]:
        if u["id"] == uid:
            u["bloqueado"] = estado
            save_users(data)
            accion = "bloqueado" if estado else "desbloqueado"
            return jsonify({"ok": True, "mensaje": f"Usuario {accion}."})
    return jsonify({"error": "Usuario no encontrado"}), 404

@app.route("/admin/usuarios/crear", methods=["POST"])
@admin_or_master_required
def admin_crear_usuario():
    d      = request.json or {}
    correo = d.get("correo", "").strip().lower()
    tipo   = d.get("tipo", "invitado")   # "invitado", "operativo" (o legacy "admin")
    role   = session.get("role")

    # Migración legacy: si llega "admin" como tipo, convertir a "operativo"
    if tipo == "admin":
        tipo = "operativo"

    # Operativo solo puede crear invitados
    if role == "operativo" and tipo != "invitado":
        return jsonify({"error": "Solo el master puede crear usuarios operativos."}), 403

    if not correo:
        return jsonify({"error": "El correo es obligatorio."}), 400
    if find_user_by_email(correo):
        return jsonify({"error": "Ese correo ya está registrado."}), 400
    nuevo = {
        "id":             str(uuid.uuid4()),
        "tipo":           tipo,
        "nombre":         d.get("nombre", "").strip(),
        "correo":         correo,
        "whatsapp":       d.get("whatsapp", "").strip(),
        "profesion":      d.get("profesion", "").strip(),
        "dedicacion":     d.get("dedicacion", "").strip(),
        "pais":           d.get("pais", "República Dominicana").strip(),
        "provincia":      d.get("provincia", "").strip(),
        "municipio":      d.get("municipio", "").strip(),
        "calle":          d.get("calle", "").strip(),
        "numero":         d.get("numero", "").strip(),
        "fecha_registro": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "bloqueado":      False
    }
    # Si es operativo y lo crea el master, guardar password_hash y forzar cambio en primer acceso
    if tipo == "operativo" and role == "master":
        pw_raw = d.get("password", "").strip()
        if pw_raw:
            nuevo["password_hash"]      = _pw_hash(pw_raw)
            nuevo["password_changed"]   = False   # forzar cambio en primer login
            nuevo["must_change_password"] = True
        else:
            nuevo["password_hash"] = ""
    # Invitado creado por admin: forzar cambio de contrasena en primer acceso
    if tipo == "invitado":
        nuevo["password_changed"] = False
    data = load_users()
    data["usuarios"].append(nuevo)
    save_users(data)
    return jsonify({"ok": True, "mensaje": f"Usuario {nuevo['nombre']} creado como {tipo}."})

@app.route("/admin/usuarios/editar", methods=["POST"])
@admin_or_master_required
def admin_editar_usuario():
    d    = request.json or {}
    uid  = d.get("id", "")
    role = session.get("role")
    # Operativo no puede editar a otro operativo
    if role == "operativo":
        target = find_user_by_id(uid)
        if target and target.get("tipo") == "operativo":
            return jsonify({"error": "No tienes permiso para editar a un operativo."}), 403
    data = load_users()
    for u in data["usuarios"]:
        if u["id"] == uid:
            campos = ["nombre","correo","whatsapp","profesion","dedicacion",
                      "pais","provincia","municipio","calle","numero","tipo"]
            for c in campos:
                if c in d:
                    val = d[c]
                    u[c] = val.strip() if isinstance(val, str) else val
            # Migración legacy: si alguien envía tipo "admin", convertir a "operativo"
            if u.get("tipo") == "admin":
                u["tipo"] = "operativo"
            save_users(data)
            return jsonify({"ok": True})
    return jsonify({"error": "Usuario no encontrado"}), 404

@app.route("/admin/usuarios/eliminar", methods=["POST"])
@admin_or_master_required
def admin_eliminar_usuario():
    uid  = (request.json or {}).get("id", "")
    role = session.get("role")
    # Operativo no puede eliminar a otro operativo
    if role == "operativo":
        target = find_user_by_id(uid)
        if target and target.get("tipo") == "operativo":
            return jsonify({"error": "No tienes permiso para eliminar a un operativo."}), 403
    data = load_users()
    orig = len(data["usuarios"])
    data["usuarios"] = [u for u in data["usuarios"] if u["id"] != uid]
    if len(data["usuarios"]) == orig:
        return jsonify({"error": "Usuario no encontrado"}), 404
    save_users(data)
    return jsonify({"ok": True})

@app.route("/cambiar-contrasena", methods=["POST"])
@login_required
def cambiar_contrasena():
    ip = _get_client_ip()
    if _rate_limited(f"pwchange:{ip}", 'password_change'):
        return jsonify({"error": "Demasiados intentos. Espera 10 minutos."}), 429

    d                = request.json or {}
    tipoPassCambiar  = d.get("tipo", "")
    actual           = d.get("actual", "")
    nueva            = d.get("nueva", "")
    confirmacion     = d.get("confirmacion", "")
    primer_acceso    = d.get("primer_acceso", False)   # True cuando es el primer cambio obligatorio
    role             = session.get("role", "")
    es_primer_acceso = primer_acceso or session.get("must_change_password", False)

    # En primer acceso NO se requiere "actual" (el usuario ya se autenticó al hacer login)
    if not es_primer_acceso and not actual:
        return jsonify({"error": "Ingresa tu contraseña actual."}), 400
    if not nueva or not confirmacion:
        return jsonify({"error": "Ingresa y confirma la nueva contraseña."}), 400
    if nueva != confirmacion:
        return jsonify({"error": "Las contraseñas no coinciden. Verifica e intenta de nuevo."}), 400
    if len(nueva) < 6:
        return jsonify({"error": "La contraseña debe tener al menos 6 caracteres."}), 400

    nueva_hash = _pw_hash(nueva)
    passwords  = load_passwords()

    correo_session = session.get("correo", "")
    nombre_session = session.get("nombre", "")

    # ── Cambiar contraseña maestra (solo master) ──
    if tipoPassCambiar in ("admin", "master"):
        if role != "master":
            return jsonify({"error": "Solo el master puede cambiar esta contraseña."}), 403
        ok_cur, _ = _pw_verify(actual, passwords.get("master", _DEFAULT_MASTER_HASH))
        if not ok_cur:
            return jsonify({"error": "La contraseña actual es incorrecta."}), 400
        passwords["master"] = nueva_hash
        save_passwords(passwords)
        log_historial(correo_session, nombre_session, "cambio_contrasena", "Cambió la contraseña maestra")
        return jsonify({"ok": True, "mensaje": "Contraseña maestra actualizada correctamente."})

    # ── Operativo cambia su propia contraseña per-user ──
    elif tipoPassCambiar == "operativo":
        if role != "operativo":
            return jsonify({"error": "Solo un operativo puede cambiar su propia contraseña."}), 403
        usuario = find_user_by_email(correo_session)
        if not usuario:
            return jsonify({"error": "Usuario no encontrado."}), 404
        # Solo verificar contraseña actual si NO es primer acceso
        if not es_primer_acceso:
            ok_cur, _ = _pw_verify(actual, usuario.get("password_hash", ""))
            if not ok_cur:
                return jsonify({"error": "La contraseña actual es incorrecta."}), 400
        # Actualizar password_hash y marcar que ya cambio la contrasena
        data = load_users()
        for u in data["usuarios"]:
            if u["correo"].lower() == correo_session.lower():
                u["password_hash"]      = nueva_hash
                u["password_changed"]   = True
                u["must_change_password"] = False
                break
        save_users(data)
        session["must_change_password"] = False
        es_primer_cambio = not usuario.get("password_changed", False)
        detalle_op = "Cambio de contraseña obligatorio (primer acceso)" if es_primer_cambio else "Cambio de contraseña personal"
        log_historial(correo_session, nombre_session, "cambio_contrasena", detalle_op)
        session.pop("_first_access_pwd", None)
        return jsonify({"ok": True, "mensaje": "Contraseña actualizada correctamente. Bienvenido/a al sistema."})

    # ── Cambiar contraseña compartida de invitados ──
    elif tipoPassCambiar == "invitado":
        if role in ("master", "operativo"):
            # Master y operativo pueden cambiar la clave de invitado sin verificar la actual
            passwords["invitado"] = nueva_hash
            save_passwords(passwords)
            log_historial(correo_session, nombre_session, "cambio_contrasena", f"{role} cambió la contraseña de invitados")
            return jsonify({"ok": True, "mensaje": "Contraseña de invitado actualizada correctamente."})
        elif role == "invitado":
            # Solo verificar contraseña actual si NO es primer acceso
            if not es_primer_acceso:
                usuario = find_user_by_email(correo_session)
                user_pw_hash = usuario.get("password_hash", "") if usuario else ""
                if user_pw_hash:
                    ok_cur, _ = _pw_verify(actual, user_pw_hash)
                else:
                    ok_cur, _ = _pw_verify(actual, passwords.get("invitado", _DEFAULT_GUEST_HASH))
                if not ok_cur:
                    return jsonify({"error": "La contraseña actual es incorrecta."}), 400
            # Store personal password_hash per user (NOT changing shared password)
            data = load_users()
            for u in data["usuarios"]:
                if u["correo"].lower() == correo_session.lower():
                    u["password_hash"]        = nueva_hash
                    u["password_changed"]     = True
                    u["must_change_password"] = False
                    break
            save_users(data)
            session["must_change_password"] = False
            detalle_inv = "Creó su contraseña personal (primer acceso)" if es_primer_acceso else "Cambió su contraseña"
            log_historial(correo_session, nombre_session, "cambio_contrasena", detalle_inv)
            session.pop("_first_access_pwd", None)
            return jsonify({"ok": True, "mensaje": "¡Contraseña creada! Bienvenido/a al sistema."})
        else:
            return jsonify({"error": "Acceso denegado."}), 403
    else:
        return jsonify({"error": "Tipo de contraseña no válido."}), 400


@app.route("/recuperar", methods=["GET", "POST"])
def recuperar():
    if request.method == "GET":
        return render_template("recuperar.html", mensaje=None, error=None)

    correo = request.form.get("correo", "").strip().lower()
    tipo   = request.form.get("tipo", "invitado")   # "admin" o "invitado"

    if not correo:
        return render_template("recuperar.html", error="Ingresa tu correo.", mensaje=None)

    # ── Rate limit ──
    ip = _get_client_ip()
    if _rate_limited(f"recovery:{ip}", 'recovery'):
        return render_template("recuperar.html", error="Demasiados intentos. Espera 10 minutos.", mensaje=None)

    # Validar que el correo exista (excepto admin maestro)
    if tipo == "invitado":
        usuario = find_user_by_email(correo)
        if not usuario:
            return render_template("recuperar.html", error="No se pudo procesar la solicitud.", mensaje=None)
        nombre = usuario["nombre"]
    else:
        nombre = "Administrador"

    # Generar código seguro de 6 dígitos (criptográficamente aleatorio)
    codigo = str(secrets.randbelow(900000) + 100000)
    codigo_hash = hashlib.sha256(codigo.encode()).hexdigest()

    data = load_recovery()
    # Cancelar solicitudes previas del mismo correo
    data["solicitudes"] = [s for s in data["solicitudes"] if s["correo"] != correo]
    data["solicitudes"].append({
        "id":          str(uuid.uuid4()),
        "correo":      correo,
        "nombre":      nombre,
        "tipo":        tipo,
        "codigo_hash": codigo_hash,
        "codigo_temp": codigo,      # Admin lo ve en el panel
        "estado":      "pendiente",
        "fecha":       datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "expira":      (datetime.now() + timedelta(minutes=15)).strftime("%Y-%m-%d %H:%M:%S"),
        "intentos":    0
    })
    save_recovery(data)
    log_historial(correo, nombre, "recuperacion_solicitada", f"Solicitó recuperación de contraseña ({tipo})")

    wa_msg = f"Hola%20{nombre},%20tu%20c%C3%B3digo%20de%20recuperaci%C3%B3n%20es:%20*{codigo}*%20%F0%9F%94%91%20%0AApp:%20{_RAILWAY_PUBLIC_URL}"
    wa_url = f"https://wa.me/{WHATSAPP_ADMIN}?text={wa_msg}"

    return render_template("recuperar.html", mensaje="Solicitud enviada. El administrador recibirá tu pedido y te enviará el código por WhatsApp.", error=None, wa_url=wa_url)


@app.route("/recuperar/verificar", methods=["POST"])
def recuperar_verificar():
    ip     = _get_client_ip()
    correo = (request.json or {}).get("correo", "").strip().lower()
    codigo = (request.json or {}).get("codigo", "").strip()
    nueva  = (request.json or {}).get("nueva", "").strip()

    if not correo or not codigo or not nueva:
        return jsonify({"error": "Todos los campos son obligatorios."}), 400

    # ── Rate limit por IP ──
    if _rate_limited(f"recovery_verify:{ip}", 'recovery_verify'):
        return jsonify({"error": "Demasiados intentos. Espera 5 minutos."}), 429

    if len(nueva) < 6:
        return jsonify({"error": "La nueva contraseña debe tener al menos 6 caracteres."}), 400

    data = load_recovery()
    sol  = next((s for s in data["solicitudes"] if s["correo"] == correo and s["estado"] == "pendiente"), None)
    if not sol:
        return jsonify({"error": "No hay solicitud pendiente para este correo."}), 404

    # ── Verificar expiración (15 minutos) ──
    expira_str = sol.get("expira")
    if expira_str:
        try:
            if datetime.now() > datetime.strptime(expira_str, "%Y-%m-%d %H:%M:%S"):
                sol["estado"] = "expirada"
                save_recovery(data)
                return jsonify({"error": "El código ha expirado. Solicita uno nuevo."}), 400
        except ValueError:
            pass

    # ── Limitar intentos fallidos (máx 5) ──
    intentos = sol.get("intentos", 0)
    if intentos >= 5:
        sol["estado"] = "bloqueada"
        save_recovery(data)
        return jsonify({"error": "Demasiados intentos fallidos. Solicita un código nuevo."}), 400

    if hashlib.sha256(codigo.encode()).hexdigest() != sol["codigo_hash"]:
        sol["intentos"] = intentos + 1
        save_recovery(data)
        return jsonify({"error": f"Código incorrecto. Quedan {5 - intentos - 1} intentos."}), 400

    # Cambiar contraseña
    passwords = load_passwords()
    nueva_hash = hashlib.sha256(nueva.encode()).hexdigest()
    if sol["tipo"] in ("admin", "master"):
        passwords["master"] = nueva_hash
    else:
        passwords["invitado"] = nueva_hash
        # Marcar password_changed
        udata = load_users()
        for u in udata["usuarios"]:
            if u["correo"].lower() == correo:
                u["password_changed"] = True
                break
        save_users(udata)
    save_passwords(passwords)

    # Marcar solicitud como usada
    sol["estado"] = "completada"
    save_recovery(data)
    log_historial(correo, sol["nombre"], "recuperacion_completada", "Contraseña recuperada exitosamente")

    return jsonify({"ok": True, "mensaje": "Contraseña cambiada exitosamente. Ya puedes iniciar sesión."})


@app.route("/admin/recuperaciones")
@admin_or_master_required
def admin_recuperaciones():
    return jsonify(load_recovery())

@app.route("/admin/recuperaciones/eliminar", methods=["POST"])
@admin_or_master_required
def admin_recuperaciones_eliminar():
    rid  = (request.json or {}).get("id", "")
    data = load_recovery()
    data["solicitudes"] = [s for s in data["solicitudes"] if s["id"] != rid]
    save_recovery(data)
    return jsonify({"ok": True})


@app.route("/solicitar-baja", methods=["POST"])
@login_required
def solicitar_baja():
    if session.get("role") != "invitado":
        return jsonify({"error": "Only guest users can request unsubscription."}), 403

    d             = request.json or {}
    porque        = d.get("porque", "").strip()
    opinion       = d.get("opinion", "").strip()
    recomendacion = d.get("recomendacion", "").strip()

    if not porque or not opinion or not recomendacion:
        return jsonify({"error": "All fields are required."}), 400

    correo = session.get("correo", "")
    nombre = session.get("nombre", "")

    # Construir el cuerpo del correo
    asunto = f"Unsubscribe Request — {nombre} ({correo})"
    cuerpo = (
        f"UNSUBSCRIBE REQUEST\n"
        f"{'='*50}\n\n"
        f"User: {nombre}\n"
        f"Email: {correo}\n"
        f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        f"{'='*50}\n\n"
        f"1. WHY DO YOU WANT TO UNSUBSCRIBE?\n{porque}\n\n"
        f"2. WHAT IS YOUR OPINION OF THE APP?\n{opinion}\n\n"
        f"3. WHAT RECOMMENDATIONS WOULD YOU GIVE?\n{recomendacion}\n\n"
        f"{'='*50}\n"
        f"To APPROVE the unsubscription, reply to this email confirming the account deletion.\n"
        f"App: {_RAILWAY_PUBLIC_URL}\n"
    )

    # Construir enlace mailto para que el servidor abra el cliente de correo
    import urllib.parse
    mailto_url = (
        f"mailto:{DISTRIBUTION_EMAIL}"
        f"?subject={urllib.parse.quote(asunto)}"
        f"&body={urllib.parse.quote(cuerpo)}"
    )

    log_historial(correo, nombre, "solicitud_baja", "Solicitó darse de baja")

    return jsonify({"ok": True, "mailto": mailto_url,
                    "asunto": asunto, "cuerpo": cuerpo,
                    "destino": DISTRIBUTION_EMAIL})


@app.route("/admin/cuadernos")
@admin_or_master_required
def admin_cuadernos():
    return jsonify({"cuadernos": get_notebooks()})

@app.route("/admin/cuadernos/guardar", methods=["POST"])
@admin_or_master_required
def admin_cuadernos_guardar():
    d      = request.json or {}
    nombre = d.get("nombre", "").strip()
    nid    = d.get("id", "").strip()
    emoji  = d.get("emoji", "📚").strip()
    uid    = d.get("uid", "")   # Si existe → editar; si vacío → crear

    if not nombre or not nid:
        return jsonify({"error": "Nombre e ID son obligatorios."}), 400

    lista = load_cuadernos()
    if uid:
        # Editar existente
        for c in lista:
            if c.get("uid") == uid or c.get("id") == uid:
                c["nombre"] = nombre
                c["id"]     = nid
                c["emoji"]  = emoji
                break
        else:
            return jsonify({"error": "Cuaderno no encontrado."}), 404
    else:
        # Crear nuevo — verificar que el ID no exista
        if any(c["id"] == nid for c in lista):
            return jsonify({"error": "Ya existe un cuaderno con ese ID."}), 400
        lista.append({"id": nid, "nombre": nombre, "emoji": emoji, "uid": str(uuid.uuid4())})

    save_cuadernos(lista)
    return jsonify({"ok": True, "cuadernos": lista})

@app.route("/admin/cuadernos/eliminar", methods=["POST"])
@admin_or_master_required
def admin_cuadernos_eliminar():
    nid   = (request.json or {}).get("id", "")
    lista = load_cuadernos()
    orig  = len(lista)
    lista = [c for c in lista if c["id"] != nid]
    if len(lista) == orig:
        return jsonify({"error": "Cuaderno no encontrado."}), 404
    save_cuadernos(lista)
    return jsonify({"ok": True, "cuadernos": lista})

@app.route("/admin/cuadernos/reordenar", methods=["POST"])
@admin_or_master_required
def admin_cuadernos_reordenar():
    orden = (request.json or {}).get("orden", [])  # lista de IDs en nuevo orden
    lista = load_cuadernos()
    mapa  = {c["id"]: c for c in lista}
    nueva = [mapa[i] for i in orden if i in mapa]
    # Agregar los que no estén en el orden (por seguridad)
    ids_nuevos = set(orden)
    nueva += [c for c in lista if c["id"] not in ids_nuevos]
    save_cuadernos(nueva)
    return jsonify({"ok": True})


@app.route("/admin/historial")
@admin_or_master_required
def admin_historial():
    return jsonify(load_historial())

@app.route("/admin/historial/eliminar", methods=["POST"])
@master_required
def admin_historial_eliminar():
    rid  = (request.json or {}).get("id", "")
    data = load_historial()
    orig = len(data["registros"])
    data["registros"] = [r for r in data["registros"] if r["id"] != rid]
    if len(data["registros"]) == orig:
        return jsonify({"error": "Registro no encontrado"}), 404
    save_historial(data)
    return jsonify({"ok": True})

@app.route("/admin/historial/limpiar", methods=["POST"])
@master_required
def admin_historial_limpiar():
    save_historial({"registros": []})
    return jsonify({"ok": True})


# ══════════════════════════════════════════════════════════════════════════
# SISTEMA DE CORRECCION REMOTA — Master y Operativo corrigen desde la app
# ══════════════════════════════════════════════════════════════════════════

_ERRORES_FILE = _DATA_DIR / "errores_reportados.json"


def _load_errores():
    try:
        if _ERRORES_FILE.exists():
            with open(_ERRORES_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {"errores": []}


def _save_errores(data):
    with open(_ERRORES_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


@app.route("/admin/reportar-error", methods=["POST"])
@admin_or_master_required
def admin_reportar_error():
    """Master u Operativo reportan un error desde la app movil."""
    d = request.json or {}
    tipo = d.get("tipo", "")  # gravamen, codigo, respuesta, otro
    codigo = d.get("codigo", "").strip()
    descripcion = d.get("descripcion", "").strip()
    valor_actual = d.get("valor_actual", "").strip()
    valor_correcto = d.get("valor_correcto", "").strip()
    consulta_original = d.get("consulta_original", "").strip()

    if not descripcion:
        return jsonify({"error": "Describe el error encontrado"}), 400

    errores = _load_errores()
    error_entry = {
        "id": str(uuid.uuid4())[:8],
        "tipo": tipo or "otro",
        "codigo": codigo,
        "descripcion": descripcion,
        "valor_actual": valor_actual,
        "valor_correcto": valor_correcto,
        "consulta_original": consulta_original,
        "reportado_por": session.get("nombre", session.get("role", "?")),
        "rol": session.get("role", "?"),
        "fecha": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "estado": "pendiente",
        "correccion_aplicada": ""
    }
    errores["errores"].insert(0, error_entry)
    _save_errores(errores)

    # Si el tipo es gravamen y hay codigo + valor_correcto, aplicar correccion automatica
    correccion_auto = False
    if tipo == "gravamen" and codigo and valor_correcto:
        resultado = _aplicar_correccion_gravamen(codigo, valor_correcto, error_entry["id"])
        if resultado:
            correccion_auto = True

    return jsonify({"ok": True, "id": error_entry["id"], "correccion_automatica": correccion_auto})


def _aplicar_correccion_gravamen(codigo, valor_correcto, error_id):
    """Corrige un gravamen en el cache del Arancel."""
    import re as _re
    cache_path = os.path.join(SKILL_DIR, "data", "fuentes_nomenclatura", "arancel_cache.json")
    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            cache = json.load(f)
        codigos = cache.get("codigos", {})
        if codigo not in codigos:
            print(f"[CORRECCION] Codigo {codigo} no existe en cache — no se puede corregir")
            return False
        desc_actual = codigos[codigo]
        # Reemplazar gravamen al final de la descripcion
        nuevo = _re.sub(r'\s+\d+\s*$', f' {valor_correcto}', desc_actual)
        if nuevo == desc_actual:
            # Sin numero al final — agregar
            nuevo = f"{desc_actual} {valor_correcto}"
        codigos[codigo] = nuevo
        cache["codigos"] = codigos
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
        # Marcar error como resuelto
        errores = _load_errores()
        for e in errores["errores"]:
            if e["id"] == error_id:
                e["estado"] = "corregido"
                e["correccion_aplicada"] = f"Cache actualizado: {codigo} gravamen → {valor_correcto}%"
                break
        _save_errores(errores)
        # Proteger en blacklist para que no se sobreescriba en re-extraccion
        try:
            bl = _cargar_blacklist()
            bl["correcciones"][codigo] = {
                "gravamen": valor_correcto,
                "fecha": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "reportado_por": "auto-correccion"
            }
            bl["historial"].append({
                "codigo": codigo, "gravamen": valor_correcto,
                "fecha": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "reportado_por": "auto-correccion"
            })
            _guardar_blacklist(bl)
            print(f"[CORRECCION] {codigo} protegido en blacklist (anti-regresion)")
        except Exception as bex:
            print(f"[CORRECCION] No se pudo proteger en blacklist: {bex}")
        print(f"[CORRECCION] Gravamen de {codigo} corregido a {valor_correcto}% en cache")
        return True
    except Exception as ex:
        print(f"[CORRECCION] Error aplicando correccion: {ex}")
        return False


@app.route("/admin/errores", methods=["GET"])
@admin_or_master_required
def admin_errores():
    """Lista errores reportados."""
    errores = _load_errores()
    return jsonify(errores)


@app.route("/admin/corregir-gravamen", methods=["POST"])
@master_required
def admin_corregir_gravamen():
    """Master corrige manualmente un gravamen en el cache."""
    d = request.json or {}
    codigo = d.get("codigo", "").strip()
    gravamen = d.get("gravamen", "").strip()

    if not codigo or gravamen == "":
        return jsonify({"error": "Codigo y gravamen son requeridos"}), 400

    # Formato SON DGA: 8 dígitos (XXXX.XX.XX) o con apertura nacional (XXXX.XX.XX.XX)
    if not _validar_son(codigo):
        return jsonify({"error": "Formato SON invalido. Use XXXX.XX.XX o XXXX.XX.XX.XX"}), 400

    grav_dec = _parse_gravamen(gravamen)
    if grav_dec is None:
        return jsonify({"error": "Gravamen debe ser un numero entre 0 y 100 (ej: 18, 18.5, 0)"}), 400

    # Normalizar para persistencia: entero si no tiene decimales, sino Decimal str
    grav_str = str(int(grav_dec)) if grav_dec == grav_dec.to_integral_value() else format(grav_dec.normalize(), "f")

    ok = _aplicar_correccion_gravamen(codigo, grav_str, f"manual-{codigo}")
    if ok:
        return jsonify({"ok": True, "mensaje": f"Gravamen de {codigo} actualizado a {grav_str}%"})
    return jsonify({"error": f"No se pudo corregir {codigo}. Verifica que exista en el cache."}), 404


@app.route("/admin/reconsultar", methods=["POST"])
@admin_or_master_required
def admin_reconsultar():
    """Reprocesa una consulta que dio error — Master u Operativo la ejecutan de nuevo."""
    d = request.json or {}
    question = d.get("question", "").strip()
    notebook_id = d.get("notebook_id", "biblioteca-de-nomenclaturas")

    if not question:
        return jsonify({"error": "Escribe la consulta a reprocesar"}), 400

    try:
        answer = ask_notebooklm(question, notebook_id, timeout=90)
        return jsonify({"answer": answer, "ok": True})
    except Exception as e:
        return jsonify({"error": f"Error al reprocesar: {str(e)[:200]}"}), 500


@app.route("/admin/estado-cache", methods=["GET"])
@admin_or_master_required
def admin_estado_cache():
    """Devuelve estado del cache del Arancel para diagnostico."""
    cache_path = os.path.join(SKILL_DIR, "data", "fuentes_nomenclatura", "arancel_cache.json")
    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            cache = json.load(f)
        codigos = cache.get("codigos", {})
        caps = {}
        for c in codigos:
            cap = c[:2]
            caps[cap] = caps.get(cap, 0) + 1
        return jsonify({
            "total_codigos": len(codigos),
            "fuente": cache.get("fuente", "?"),
            "fecha": cache.get("fecha_extraccion", "?"),
            "capitulos": len(caps),
            "top_capitulos": dict(sorted(caps.items(), key=lambda x: -x[1])[:10])
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/admin/errores-resueltos", methods=["GET"])
@admin_or_master_required
def admin_errores_resueltos():
    """Consulta la biblioteca de errores resueltos (anti-regresion)."""
    errores_path = os.path.join(SKILL_DIR, "data", "fuentes_nomenclatura", "errores_resueltos.json")
    codigo = request.args.get("codigo", "").strip()
    try:
        if not os.path.exists(errores_path):
            return jsonify({"errores": [], "total": 0})
        with open(errores_path, "r", encoding="utf-8") as f:
            errores = json.load(f)
        if codigo:
            errores = [e for e in errores if
                       e.get("codigo_original") == codigo or
                       e.get("codigo_corregido") == codigo]
        # Estadisticas rapidas
        total_ocurrencias = sum(e.get("ocurrencias", 1) for e in errores)
        fuentes = {}
        for e in errores:
            src = e.get("fuente", "desconocido")
            fuentes[src] = fuentes.get(src, 0) + 1
        return jsonify({
            "errores": errores,
            "total": len(errores),
            "total_ocurrencias": total_ocurrencias,
            "por_fuente": fuentes
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/admin/errores-recurrentes", methods=["GET"])
@admin_or_master_required
def admin_errores_recurrentes():
    """Consulta errores recurrentes documentados (anti-regresion general)."""
    recurrentes_path = os.path.join(SKILL_DIR, "data", "errores_recurrentes.json")
    try:
        if not os.path.exists(recurrentes_path):
            return jsonify({"errores": [], "total": 0, "reglas": []})
        with open(recurrentes_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        errores = data.get("errores", [])
        tipo_filtro = request.args.get("tipo", "").strip()
        estado_filtro = request.args.get("estado", "").strip()
        if tipo_filtro:
            errores = [e for e in errores if e.get("tipo") == tipo_filtro]
        if estado_filtro:
            errores = [e for e in errores if e.get("estado") == estado_filtro]
        # Ordenar por mas reportados primero
        errores.sort(key=lambda e: e.get("reportado", 0), reverse=True)
        return jsonify({
            "errores": errores,
            "total": len(errores),
            "reglas_prevencion": data.get("reglas_prevencion", [])
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/admin/buscar-cache", methods=["GET"])
@admin_or_master_required
def admin_buscar_cache():
    """Busca un codigo en el cache y devuelve su info."""
    codigo = request.args.get("codigo", "").strip()
    if not codigo:
        return jsonify({"error": "Parametro 'codigo' requerido"}), 400
    cache_path = os.path.join(SKILL_DIR, "data", "fuentes_nomenclatura", "arancel_cache.json")
    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            cache = json.load(f)
        codigos = cache.get("codigos", {})
        if codigo in codigos:
            desc = codigos[codigo]
            import re as _re
            m = _re.search(r'\s+(\d+)\s*$', desc.strip())
            grav = m.group(1) if m else "?"
            return jsonify({"existe": True, "codigo": codigo, "descripcion": desc, "gravamen": grav})
        # Buscar parcial (primeros 4 o 6 digitos)
        parciales = {k: v for k, v in codigos.items() if k.startswith(codigo[:4])}
        return jsonify({"existe": False, "codigo": codigo, "sugerencias": dict(list(parciales.items())[:10])})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Auditoria del Cache Arancel (self-healing) ────────────────────────
_BLACKLIST_FILE = os.path.join(SKILL_DIR, "data", "fuentes_nomenclatura", "correcciones_manuales.json")


def _cargar_blacklist():
    try:
        if os.path.isfile(_BLACKLIST_FILE):
            with open(_BLACKLIST_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {"correcciones": {}, "historial": []}


def _guardar_blacklist(bl):
    with open(_BLACKLIST_FILE, "w", encoding="utf-8") as f:
        json.dump(bl, f, ensure_ascii=False, indent=2)


@app.route("/admin/compress-status", methods=["GET"])
@admin_or_master_required
def admin_compress_status():
    """Estado del sub-agente de compresion y metricas del pipeline."""
    status_file = os.path.join(SKILL_DIR, "data", "compressed", "subagent_status.json")
    stats_file = os.path.join(SKILL_DIR, "data", "compressed", "stats.json")
    zip_file = os.path.join(SKILL_DIR, "data", "compressed", "master_notebooklm.zip")
    try:
        estado = {}
        if os.path.exists(status_file):
            with open(status_file, "r", encoding="utf-8") as f:
                estado = json.load(f)
        if os.path.exists(stats_file):
            with open(stats_file, "r", encoding="utf-8") as f:
                estado["pipeline_stats"] = json.load(f)
        estado["zip_existe"] = os.path.exists(zip_file)
        if estado["zip_existe"]:
            estado["zip_kb"] = round(os.path.getsize(zip_file) / 1024, 1)
        return jsonify(estado)
    except Exception as e:
        return jsonify({"error": str(e), "estado": "sin_datos"}), 200


@app.route("/admin/compress-run", methods=["POST"])
@admin_or_master_required
def admin_compress_run():
    """Dispara el pipeline de compresion manualmente desde el panel admin."""
    import subprocess
    pipeline = os.path.join(SKILL_DIR, "scripts", "auto_compress_pipeline.py")
    modo = request.json.get("modo", "incremental") if request.is_json else "incremental"
    try:
        proc = subprocess.Popen(
            [sys.executable, pipeline, f"--modo={modo}"],
            cwd=os.path.dirname(os.path.abspath(__file__)),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return jsonify({"iniciado": True, "pid": proc.pid, "modo": modo})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/admin/auditar-cache", methods=["GET"])
@admin_or_master_required
def admin_auditar_cache():
    """Auditoria de salud del cache del Arancel."""
    import re as _re
    cache_path = os.path.join(SKILL_DIR, "data", "fuentes_nomenclatura", "arancel_cache.json")
    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            cache = json.load(f)
        codigos = cache.get("codigos", {})
        sin_grav = 0
        caps = {}
        for c, desc in codigos.items():
            cap = c[:2]
            caps[cap] = caps.get(cap, 0) + 1
            m = _re.search(r'\s+(\d+)\s*$', desc.strip())
            if not m:
                sin_grav += 1
        bl = _cargar_blacklist()
        return jsonify({
            "salud": "OPTIMO" if sin_grav < 100 else "DEGRADADO" if sin_grav < 500 else "CRITICO",
            "total_codigos": len(codigos),
            "sin_gravamen": sin_grav,
            "capitulos": len(caps),
            "correcciones_protegidas": len(bl.get("correcciones", {})),
            "fecha_extraccion": cache.get("fecha_extraccion", "?"),
            "reparaciones": cache.get("reparaciones_aplicadas", 0)
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/admin/proteger-correccion", methods=["POST"])
@master_required
def admin_proteger_correccion():
    """Registra una correccion en la blacklist para que no se sobreescriba."""
    d = request.json or {}
    codigo = d.get("codigo", "").strip()
    gravamen = d.get("gravamen", "").strip()
    if not codigo or gravamen == "":
        return jsonify({"error": "Codigo y gravamen requeridos"}), 400
    bl = _cargar_blacklist()
    bl["correcciones"][codigo] = {
        "gravamen": gravamen,
        "fecha": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "reportado_por": session.get("nombre", session.get("role", "master"))
    }
    bl["historial"].append({
        "codigo": codigo, "gravamen": gravamen,
        "fecha": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "reportado_por": session.get("nombre", session.get("role", "master"))
    })
    _guardar_blacklist(bl)
    return jsonify({"ok": True, "mensaje": f"{codigo} protegido con gravamen {gravamen}%"})


# ── Capa 2: Sync Notion → SQLite ─────────────────────────────────────────
@app.route("/admin/sync-notion", methods=["POST"])
@master_required
def admin_sync_notion():
    """Sincroniza jurisprudencia, SOPs y fichas merceológicas desde Notion a SQLite."""
    dry_run = request.json.get("dry_run", False) if request.is_json else False
    try:
        import importlib.util as _ilu
        _spec = _ilu.spec_from_file_location(
            "sync_notion",
            os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "notion_service", "sync_notion_to_sqlite.py")
        )
        _mod = _ilu.module_from_spec(_spec)
        _spec.loader.exec_module(_mod)
        result = _mod.sync(dry_run=dry_run)
        return jsonify({"ok": True, **result})
    except EnvironmentError as e:
        return jsonify({"ok": False, "error": str(e),
                        "hint": "Configura NOTION_API_KEY en Railway Variables"}), 503
    except ImportError as e:
        return jsonify({"ok": False, "error": str(e),
                        "hint": "Agrega notion-client>=2.2.1 a requirements.txt"}), 503
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ── Clasificador merceológico automático (7 etapas) ──────────────────────
@app.route("/merceologia/clasificar-auto", methods=["POST"])
def merceologia_clasificar_auto():
    """
    Pipeline 7 etapas: ficha → capítulo → notas → biblioteca RAG → SON → validar → Notion.

    Body JSON:
      {
        "descripcion": "Cámara videoconferencia 4K...",
        "publicar_notion": false       // opcional (default false)
      }
    """
    if not session.get("usuario"):
        return jsonify({"ok": False, "error": "login requerido"}), 401
    data = request.get_json(silent=True) or {}
    descripcion = (data.get("descripcion") or "").strip()
    if not descripcion or len(descripcion) < 5:
        return jsonify({"ok": False, "error": "descripcion requerida (>= 5 chars)"}), 400
    publicar = bool(data.get("publicar_notion", False))
    try:
        from sub_agentes.clasificador_merceologico_auto import clasificar_producto
        result = clasificar_producto(descripcion, publicar=publicar)
        return jsonify({"ok": True, **result})
    except Exception as e:
        import traceback
        return jsonify({"ok": False, "error": str(e),
                        "trace": traceback.format_exc()[:2000]}), 500


@app.route("/biblioteca/buscar")
def biblioteca_buscar():
    """Busqueda FTS5 sobre los 11 PDFs de biblioteca-nomenclatura."""
    if not session.get("usuario"):
        return jsonify({"ok": False, "error": "login requerido"}), 401
    q = (request.args.get("q") or "").strip()
    cap = (request.args.get("capitulo") or "").strip() or None
    try:
        limit = max(1, min(int(request.args.get("limit", 5)), 20))
    except ValueError:
        limit = 5
    if not q:
        return jsonify({"ok": False, "error": "q requerido"}), 400
    try:
        from sub_agentes.investigador_biblioteca import investigar
        keywords = [w for w in re.split(r"\s+", q) if len(w) >= 3]
        res = investigar(keywords, capitulo=cap, limit=limit)
        return jsonify({"ok": True, "q": q, "capitulo": cap,
                        "resultados": res, "total": len(res)})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ── Diagnóstico del sistema de consultas (Gemini + NotebookLM) ───────────
@app.route("/admin/diagnostico-notebooklm")
@master_required
def admin_diagnostico_notebooklm():
    """Prueba el backend activo de consultas: primero Gemini, luego NotebookLM navegador."""
    TEST_Q  = "Di exactamente la palabra OK y nada más."
    TEST_NB = "biblioteca-de-nomenclaturas"
    gemini_key = os.environ.get("GEMINI_API_KEY", "")
    report = {
        "python":    PYTHON,
        "skill_dir": SKILL_DIR,
        "is_cloud":  _IS_CLOUD,
        "gemini_key_set": bool(gemini_key),
        "gemini_key_hint": "***configurada***" if gemini_key else "NO CONFIGURADA",
    }

    # ── Test Gemini ────────────────────────────────────────────────────
    if gemini_key:
        cmd_g = [PYTHON, "scripts/ask_gemini.py",
                 "--question", TEST_Q,
                 "--notebook-id", TEST_NB]
        env_g = os.environ.copy()
        env_g["PYTHONIOENCODING"] = "utf-8"
        env_g["PYTHONPATH"] = SKILL_DIR
        try:
            rg = subprocess.run(cmd_g, cwd=SKILL_DIR,
                                capture_output=True, text=True, encoding="utf-8",
                                env=env_g, timeout=60)
            report["gemini_rc"]     = rg.returncode
            report["gemini_stdout"] = rg.stdout[:1500]
            report["gemini_stderr"] = rg.stderr[:500]
            report["gemini_status"] = "OK" if rg.returncode == 0 and rg.stdout.strip() else "FALLO"
        except Exception as e:
            report["gemini_status"] = f"EXCEPCION: {e}"
    else:
        report["gemini_status"] = "OMITIDO — agrega GEMINI_API_KEY en Railway > Variables"

    # ── Test NotebookLM navegador (informativo) ────────────────────────
    cmd_n = [PYTHON, "scripts/ask_question.py",
             "--question", TEST_Q,
             "--notebook-id", TEST_NB]
    env_n = os.environ.copy()
    env_n["PYTHONIOENCODING"] = "utf-8"
    env_n["PYTHONPATH"] = SKILL_DIR
    env_n.pop("DISPLAY", None)
    if not env_n.get("PLAYWRIGHT_BROWSERS_PATH"):
        env_n["PLAYWRIGHT_BROWSERS_PATH"] = "/ms-playwright"
    try:
        rn = subprocess.run(cmd_n, cwd=SKILL_DIR,
                            capture_output=True, text=True, encoding="utf-8",
                            env=env_n, timeout=60)
        report["notebooklm_rc"]     = rn.returncode
        report["notebooklm_stdout"] = rn.stdout[:1500]
        report["notebooklm_stderr"] = rn.stderr[:500]
        report["notebooklm_status"] = "OK" if rn.returncode == 0 else "FALLO (normal en nube)"
    except Exception as e:
        report["notebooklm_status"] = f"EXCEPCION: {e}"

    return jsonify(report)

GUIA_FILE = str((_BASE / "app/guia_instalacion.txt") if _IS_CLOUD else Path(r"C:\Users\Usuario\Desktop\Biblioteca Notebooklm DGA\servidor-movil\guia_instalacion.txt"))

# ── Guía de instalación ──────────────────────────────────────────────────
@app.route("/guia")
@login_required
def guia():
    try:
        with open(GUIA_FILE, "r", encoding="utf-8") as f:
            contenido = f.read()
    except Exception:
        contenido = ""
    role       = session.get("role", "invitado")
    server_url = _get_public_url()
    qr_b64     = _gen_qr_base64(server_url)
    return render_template("guia.html", contenido=contenido, role=role, server_url=server_url, qr_b64=qr_b64)

@app.route("/guia/guardar", methods=["POST"])
@login_required
def guia_guardar():
    if session.get("role") != "master":
        return jsonify({"error": "Solo el master puede editar."}), 403
    contenido = request.json.get("contenido", "")
    try:
        with open(GUIA_FILE, "w", encoding="utf-8") as f:
            f.write(contenido)
        return jsonify({"ok": True})
    except Exception as e:
        print(f"[GUIA_ERROR] {e}")
        return jsonify({"error": "Error al guardar la guía."}), 500

# ── Instalador / Descarga App ────────────────────────────────────────────
# URL pública ngrok (se detecta automáticamente si está activo)
def _get_public_url():
    """Devuelve la URL pública correcta según el entorno."""
    # En Railway: usar la URL del dominio configurado
    railway_url = os.environ.get("RAILWAY_PUBLIC_DOMAIN")
    if railway_url:
        return f"https://{railway_url}"
    # URL centralizada del despliegue en Railway
    if _IS_CLOUD:
        return _RAILWAY_PUBLIC_URL
    # Local: intentar ngrok, si no IP local
    try:
        import urllib.request, json as _json
        with urllib.request.urlopen("http://localhost:4040/api/tunnels", timeout=1) as r:
            data = _json.loads(r.read())
            tunnels = data.get("tunnels", [])
            for t in tunnels:
                if t.get("proto") == "https":
                    return t["public_url"]
            if tunnels:
                return tunnels[0]["public_url"]
    except Exception:
        pass
    import socket
    return f"http://{socket.gethostbyname(socket.gethostname())}:5000"

def _get_local_ip():
    import socket
    return socket.gethostbyname(socket.gethostname())

def _gen_qr_base64(url):
    try:
        import qrcode, io, base64 as b64
        qr = qrcode.QRCode(version=1, box_size=10, border=3,
                           error_correction=qrcode.constants.ERROR_CORRECT_M)
        qr.add_data(url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="#d4af37", back_color="#0f172a")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return b64.b64encode(buf.getvalue()).decode()
    except Exception:
        return None

@app.route("/manual/admin")
@login_required
def manual_admin():
    if session.get("role") not in ("master", "operativo"):
        return redirect(url_for("manual_invitado"))
    return render_template("manual_admin.html", public_url=_get_public_url())

@app.route("/manual/invitado")
@login_required
def manual_invitado():
    return render_template("manual_invitado.html")

@app.route("/manual/pdf/<rol>")
@login_required
def manual_pdf(rol):
    """Descarga el manual PDF del rol correspondiente."""
    if rol == "admin":
        if session.get("role") not in ("master", "operativo"):
            return redirect(url_for("index"))
        filename = "Manual_Administrador_Aduanas_RD.pdf"
    else:
        filename = "Manual_Invitado_Aduanas_RD.pdf"
    return send_from_directory(
        os.path.join(app.static_folder),
        filename,
        as_attachment=True,
        download_name=filename,
    )

@app.route("/api/segunda-opinion", methods=["POST"])
@login_required
def api_segunda_opinion():
    """Busca top-5 codigos del cache priorizando mismo CAPITULO del codigo primario
    y mismo capitulo de la ficha merceologica (si existe).

    Regla tecnica: primero se determina la merceologia del producto (titulo/capitulo
    del Arancel 7ma Enmienda), luego se buscan codigos candidatos dentro de ese
    mismo capitulo con caracteristicas similares. Solo si no hay candidatos
    suficientes dentro del capitulo se abre a otros capitulos, penalizando el score.
    """
    import re as _re
    d = request.json or {}
    query = d.get("query", "").strip()
    codigo_actual = d.get("codigo_actual", "").strip()
    if not query:
        return jsonify({"error": "query requerida"}), 400

    cache_path = os.path.join(SKILL_DIR, "data", "fuentes_nomenclatura", "arancel_cache.json")
    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            cache = json.load(f)
        codigos = cache.get("codigos", cache)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    # Capitulo del codigo primario (prioridad maxima)
    cap_primario = codigo_actual[:2] if _re.match(r'^\d{4}\.\d{2}\.\d{2}$', codigo_actual) else ""
    # Partida (4 dig) del codigo primario (bonus de cercania dentro del capitulo)
    partida_primaria = codigo_actual[:4] if cap_primario else ""

    # Capitulo desde ficha merceologica (si existe para el query)
    cap_merceologia = ""
    try:
        sys.path.insert(0, str(Path(__file__).parent / "notebooklm_skill" / "scripts"))
        from merceologia_agent import buscar_ficha_para_consulta as _buscar_ficha
        match = _buscar_ficha(query, umbral=0.35)
        if match:
            _slug, _ficha, _score = match
            cod_ficha = _ficha.get("codigo") or ""
            if _re.match(r'^\d{4}\.\d{2}\.\d{2}$', cod_ficha):
                cap_merceologia = cod_ficha[:2]
    except Exception as _e:
        print(f"[SEGUNDA-OPINION] ficha merceologica no disponible: {_e}")

    # Normalizar query: extraer palabras clave significativas (>=4 chars)
    palabras = [w.lower() for w in _re.findall(r'[a-zA-ZáéíóúüñÁÉÍÓÚÜÑ]{4,}', query)]
    if not palabras:
        return jsonify({"error": "Consulta muy corta"}), 400

    # Scoring jerarquico por capitulo
    scores = []
    for codigo, desc in codigos.items():
        if codigo == codigo_actual:
            continue
        desc_lower = desc.lower()
        score_texto = sum(2 if p in desc_lower else 0 for p in palabras)
        score_texto += sum(1 if p in desc_lower[:60] else 0 for p in palabras)
        if score_texto == 0:
            continue

        # Boost por afinidad de capitulo/partida
        cap_cand = codigo[:2]
        partida_cand = codigo[:4]
        boost = 0
        if cap_primario and cap_cand == cap_primario:
            boost += 10  # mismo capitulo que primario
            if partida_primaria and partida_cand == partida_primaria:
                boost += 5  # misma partida 4-dig (hermanos)
        if cap_merceologia and cap_cand == cap_merceologia:
            boost += 8
        # Penalizar codigos de capitulos totalmente distintos al primario y a merceologia
        if cap_primario and cap_cand != cap_primario and cap_cand != cap_merceologia:
            boost -= 6

        score_total = score_texto + boost
        if score_total <= 0:
            continue
        m = _re.search(r'\s+(\d+)\s*$', desc.strip())
        grav = m.group(1) if m else "?"
        scores.append((score_total, codigo, desc, grav, cap_cand))

    scores.sort(reverse=True)

    # Preferencia estricta: si hay >=3 candidatos del mismo capitulo primario, mostrar solo esos.
    # Si no, completar con otros respetando el score.
    mismo_cap = [s for s in scores if cap_primario and s[4] == cap_primario]
    if len(mismo_cap) >= 3:
        finales = mismo_cap[:5]
    else:
        vistos = {s[1] for s in mismo_cap}
        restantes = [s for s in scores if s[1] not in vistos]
        finales = (mismo_cap + restantes)[:5]

    top5 = [
        {"codigo": c, "descripcion": d[:120], "gravamen": g,
         "score": s, "capitulo": cap, "mismo_capitulo": bool(cap_primario and cap == cap_primario)}
        for s, c, d, g, cap in finales
    ]
    return jsonify({
        "ok": True,
        "candidatos": top5,
        "query": query,
        "palabras_clave": palabras,
        "capitulo_primario": cap_primario,
        "capitulo_merceologia": cap_merceologia,
    })


@app.route("/api/confirmar-clasificacion", methods=["POST"])
@login_required
def api_confirmar_clasificacion():
    """El usuario confirma que el codigo X es el correcto para su consulta.
    Guarda en correcciones_manuales para que future consultas lo usen."""
    import re as _re
    d = request.json or {}
    codigo = d.get("codigo", "").strip()
    query = d.get("query", "").strip()
    gravamen = d.get("gravamen", "").strip()
    if not codigo or not _re.match(r'^\d{4}\.\d{2}\.\d{2}$', codigo):
        return jsonify({"error": "Codigo invalido"}), 400

    # Registrar en correcciones con la query como contexto
    bl = _cargar_blacklist()
    bl["correcciones"][codigo] = {
        "gravamen": gravamen,
        "fecha": __import__('datetime').datetime.now().strftime("%Y-%m-%d %H:%M"),
        "reportado_por": f"segunda-opinion:{session.get('username','?')}",
        "query_origen": query[:100]
    }
    bl.setdefault("historial", []).append({
        "codigo": codigo, "gravamen": gravamen,
        "fecha": __import__('datetime').datetime.now().strftime("%Y-%m-%d %H:%M"),
        "reportado_por": f"segunda-opinion:{session.get('username','?')}",
        "query_origen": query[:100]
    })
    _guardar_blacklist(bl)
    return jsonify({"ok": True, "mensaje": f"Clasificacion {codigo} confirmada y guardada"})


@app.route("/api/validar-codigo-manual", methods=["POST"])
@login_required
def api_validar_codigo_manual():
    """Valida y describe un codigo arancelario ingresado manualmente por el usuario."""
    import re as _re
    d = request.json or {}
    codigo = d.get("codigo", "").strip().replace(" ", "")
    if not _re.match(r'^\d{4}\.\d{2}\.\d{2}$', codigo):
        return jsonify({"error": "Formato inválido. Usa: XXXX.XX.XX (ej: 9506.91.90)"}), 400

    cache_path = os.path.join(SKILL_DIR, "data", "fuentes_nomenclatura", "arancel_cache.json")
    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            cache = json.load(f)
        codigos = cache.get("codigos", cache)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    if codigo not in codigos:
        return jsonify({"existe": False, "codigo": codigo,
                        "error": f"Código {codigo} no encontrado en el Arancel RD (7,616 códigos verificados)"}), 200

    desc = codigos[codigo]
    m = _re.search(r'\s+(\d+)\s*$', desc.strip())
    gravamen = m.group(1) if m else "?"
    return jsonify({"ok": True, "existe": True, "codigo": codigo,
                    "descripcion": desc, "gravamen": gravamen})


@app.route("/api/consultar-isc-partida", methods=["POST"])
@login_required
def api_consultar_isc_partida():
    """Sub-agente ISC: consulta si una partida arancelaria lleva ISC u otros impuestos.
    Flujo: cache local → Gemini cuaderno legal → DGII tabla codificada.
    """
    import re as _re
    d = request.json or {}
    codigo = d.get("codigo", "").strip()
    descripcion = d.get("descripcion", "").strip()[:120]
    usar_gemini = d.get("usar_gemini", False)  # Por defecto rapido (sin Gemini) en UI

    if not codigo or not _re.match(r'^\d{4}\.\d{2}\.\d{2}$', codigo):
        return jsonify({"error": "Codigo invalido"}), 400

    try:
        sys.path.insert(0, str(Path(__file__).parent / "notebooklm_skill" / "scripts"))
        from consultor_isc import consultar_isc
        resultado = consultar_isc(codigo, descripcion, usar_gemini=usar_gemini)
        # Garantizar que fuente y base_legal nunca sean vacios (la card del
        # frontend debe poder mostrar el origen incluso cuando NO APLICA).
        if not resultado.get("fuente"):
            resultado["fuente"] = f"consultor_isc.py (capa fallback, cap. {codigo[:2]})"
        if not resultado.get("base_legal"):
            resultado["base_legal"] = (
                "Sin disposicion especifica en isc_lookup.json para esta partida. "
                "ISC aplica solo a capitulos 22, 24, 27, 85 (partidas afectadas), 87 — Ley 11-92 Titulo IV"
            )
        if not resultado.get("otros_cargos"):
            resultado["otros_cargos"] = "NINGUNO"
        return jsonify({"ok": True, **resultado})
    except Exception as e:
        print(f"[ISC-ENDPOINT] Error: {e}")
        # Fallback: buscar directamente en isc_lookup.json
        try:
            isc_path = os.path.join(SKILL_DIR, "data", "fuentes_nomenclatura", "isc_lookup.json")
            with open(isc_path, "r", encoding="utf-8") as f:
                isc_data = json.load(f)
            cap = codigo[:2]
            cap_data = isc_data.get("capitulos_con_isc", {}).get(cap)
            if cap_data:
                verificados = cap_data.get("codigos_verificados", {})
                if codigo in verificados:
                    entry = verificados[codigo]
                    return jsonify({"ok": True, "codigo": codigo,
                                    "isc": entry.get("isc", "NO APLICA"),
                                    "base_legal": "Ley 11-92 Art. 375, bienes suntuarios electronicos",
                                    "fuente": f"isc_lookup.json[cap.{cap}].codigos_verificados[{codigo}]",
                                    "certeza": "ALTA", "otros_cargos": "NINGUNO"})
                partidas_afectadas = cap_data.get("partidas_afectadas", [])
                if any(codigo.startswith(p) for p in partidas_afectadas):
                    return jsonify({"ok": True, "codigo": codigo,
                                    "isc": cap_data.get("tasas", {}).get("default", "NO APLICA"),
                                    "base_legal": f"Ley 11-92 — Cap. {cap} ({cap_data.get('descripcion','')})",
                                    "fuente": f"isc_lookup.json[cap.{cap}].partidas_afectadas",
                                    "certeza": "MEDIA", "otros_cargos": "NINGUNO"})
                # Capitulo tiene ISC pero esta partida NO aplica — responder explicito
                return jsonify({"ok": True, "codigo": codigo, "isc": "NO APLICA",
                                "base_legal": (f"Cap. {cap} tiene ISC solo para partidas "
                                               f"{cap_data.get('partidas_afectadas', [])}; "
                                               f"{codigo} no esta afectada."),
                                "fuente": f"isc_lookup.json[cap.{cap}] (partida fuera de afectadas)",
                                "certeza": "ALTA", "otros_cargos": "NINGUNO"})
            # Capitulo sin ISC
            return jsonify({"ok": True, "codigo": codigo, "isc": "NO APLICA",
                            "base_legal": (f"Capitulo {cap} no figura en isc_lookup.json. "
                                           "ISC RD aplica a 22 (alcoholes), 24 (tabaco), 27 (combustibles), "
                                           "85 (electronicos suntuarios), 87 (vehiculos)."),
                            "fuente": "isc_lookup.json (capitulo sin ISC registrado) — Ley 11-92 Titulo IV",
                            "certeza": "ALTA", "otros_cargos": "NINGUNO"})
        except Exception as _e2:
            pass
        return jsonify({"ok": True, "codigo": codigo, "isc": "NO DISPONIBLE",
                        "base_legal": ("No fue posible cargar isc_lookup.json en este momento. "
                                       "Reintente la verificacion en unos segundos."),
                        "fuente": f"/api/consultar-isc-partida error interno: {str(e)[:80]}",
                        "certeza": "BAJA", "otros_cargos": "NINGUNO"})


@app.route("/api/consultar-notas-arancel", methods=["POST"])
@login_required
def api_consultar_notas_arancel():
    """Consultor paralelo de Notas Legales/Explicativas del Arancel RD.
    Body: {codigo: "XXXX.XX.XX"}
    Devuelve veredicto ISC + base legal + razon citando notas del capitulo.
    """
    d = request.json or {}
    codigo = (d.get("codigo") or "").strip()
    if not codigo:
        return jsonify({"error": "codigo requerido"}), 400
    try:
        sys.path.insert(0, str(Path(__file__).parent / "notebooklm_skill" / "scripts"))
        from consultor_notas_arancel import analizar_codigo
        resultado = analizar_codigo(codigo)
        resultado["ok"] = "error" not in resultado
        return jsonify(resultado)
    except Exception as e:
        print(f"[NOTAS-ARANCEL-ENDPOINT] Error: {e}")
        return jsonify({"ok": False, "codigo": codigo, "error": str(e),
                        "veredicto": "ERROR",
                        "fuente": "/api/consultar-notas-arancel (sin cache disponible)"}), 200


# ─────────────────────────────────────────────────────────────────
# VIBEVOICE-ASR — Transcripcion + Highlights + Clips Virales
# ─────────────────────────────────────────────────────────────────

_VIBEVOICE_UPLOAD_DIR = os.path.join(
    os.path.dirname(__file__), "notebooklm_skill", "data", "vibevoice_tmp"
)
os.makedirs(_VIBEVOICE_UPLOAD_DIR, exist_ok=True)


@app.route("/api/transcribir-audio", methods=["POST"])
@login_required
def api_transcribir_audio():
    """Transcribe audio/video con VibeVoice-ASR.
    Form-data: file=<audio.mp3/mp4/wav/webm>, language=es (opcional), vocab=csv (opcional)
    """
    if "file" not in request.files:
        return jsonify({"ok": False, "error": "Debe adjuntar archivo en el campo 'file'"}), 400
    f = request.files["file"]
    if not f.filename:
        return jsonify({"ok": False, "error": "Archivo sin nombre"}), 400

    _audio_ext = os.path.splitext(f.filename)[1].lower()
    if _audio_ext not in _ALLOWED_AUDIO:
        return jsonify({"ok": False, "error": f"Formato de audio no soportado. Usa: {', '.join(sorted(_ALLOWED_AUDIO))}"}), 400

    import uuid
    safe_name = f"{uuid.uuid4().hex}{_audio_ext}"  # no usar basename del usuario — path traversal
    upload_path = os.path.join(_VIBEVOICE_UPLOAD_DIR, safe_name)
    try:
        f.save(upload_path)
    except Exception as e:
        return jsonify({"ok": False, "error": f"No se pudo guardar: {e}"}), 500

    language = (request.form.get("language") or "es").strip()
    vocab_raw = (request.form.get("vocab") or "").strip()
    vocabulary = [v.strip() for v in vocab_raw.split(",") if v.strip()] or None

    try:
        sys.path.insert(0, str(Path(__file__).parent / "notebooklm_skill" / "scripts"))
        from vibevoice_asr import transcribir
        resultado = transcribir(upload_path, language=language, vocabulary=vocabulary)
        return jsonify(resultado)
    except Exception as e:
        print(f"[VIBEVOICE-ENDPOINT] Error: {e}")
        return jsonify({"ok": False, "error": str(e)}), 200
    finally:
        try:
            os.remove(upload_path)
        except Exception:
            pass


@app.route("/api/highlights-video", methods=["POST"])
@login_required
def api_highlights_video():
    """Identifica momentos virales dentro de una transcripcion ya hecha.
    Body JSON: {segments: [{speaker, start, end, text}, ...], max_highlights?: 5}
    """
    d = request.json or {}
    segments = d.get("segments") or []
    max_h = int(d.get("max_highlights") or 5)
    if not segments:
        return jsonify({"ok": False, "error": "segments requerido"}), 400
    try:
        sys.path.insert(0, str(Path(__file__).parent / "notebooklm_skill" / "scripts"))
        from vibevoice_asr import extraer_highlights
        highlights = extraer_highlights(segments, max_highlights=max_h)
        return jsonify({"ok": True, "highlights": highlights, "total": len(highlights)})
    except Exception as e:
        print(f"[VIBEVOICE-HIGHLIGHTS] Error: {e}")
        return jsonify({"ok": False, "error": str(e)}), 200


@app.route("/api/generar-clip-viral", methods=["POST"])
@login_required
def api_generar_clip_viral():
    """Exporta clip MP4 9:16 con subtitulos quemados via ffmpeg.
    Body JSON: {video_url | video_path, start: float, end: float, titulo: str, subtitulos: [seg,...]}
    Requiere ffmpeg disponible en PATH. Si no esta, devuelve instrucciones.
    """
    import shutil
    if not shutil.which("ffmpeg"):
        return jsonify({
            "ok": False,
            "error": "ffmpeg no instalado en el servidor",
            "setup": "Instalar ffmpeg en el entorno Railway (nixpacks.toml -> packages = ['ffmpeg']) o local (apt install ffmpeg)"
        }), 200

    d = request.json or {}
    video_path = d.get("video_path") or ""
    start = float(d.get("start") or 0)
    end = float(d.get("end") or 0)
    titulo = (d.get("titulo") or "Clip DGA").strip()
    if not video_path or end <= start:
        return jsonify({"ok": False, "error": "Se requiere video_path y rango start<end"}), 400
    if not os.path.exists(video_path):
        return jsonify({"ok": False, "error": f"No existe {video_path}"}), 404

    import uuid, subprocess
    out_path = os.path.join(_VIBEVOICE_UPLOAD_DIR, f"clip_{uuid.uuid4().hex}.mp4")
    dur = end - start
    # Crop a 9:16 + escalar a 1080x1920 + subtitulo fijo con titulo
    cmd = [
        "ffmpeg", "-y",
        "-ss", str(start), "-i", video_path, "-t", str(dur),
        "-vf", (
            "crop=ih*9/16:ih,scale=1080:1920,"
            f"drawtext=text='{titulo.replace(chr(39), '')}'"
            ":fontcolor=white:fontsize=56:x=(w-text_w)/2:y=80"
            ":box=1:boxcolor=black@0.55:boxborderw=20"
        ),
        "-c:a", "aac", "-b:a", "128k", "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        out_path,
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if r.returncode != 0:
            return jsonify({"ok": False, "error": "ffmpeg fallo",
                            "stderr": r.stderr[-1000:]}), 200
        return jsonify({"ok": True, "clip_path": out_path,
                        "duracion": round(dur, 2),
                        "formato": "MP4 9:16 1080x1920 (vertical redes sociales)"})
    except subprocess.TimeoutExpired:
        return jsonify({"ok": False, "error": "ffmpeg excedio 5min"}), 200
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 200


@app.route("/api/generar-informe-pdf", methods=["POST"])
@login_required
def api_generar_informe_pdf():
    """Compara dos partidas arancelarias y devuelve un PDF descargable."""
    d           = request.json or {}
    query       = d.get("query", "").strip()
    codigo_a    = d.get("codigo_a", "").strip()   # recomendado por Biblioteca
    codigo_b    = d.get("codigo_b", "").strip()   # seleccionado por usuario
    gravamen_a  = str(d.get("gravamen_a", ""))
    gravamen_b  = str(d.get("gravamen_b", ""))

    if not codigo_a or not codigo_b:
        return jsonify({"error": "Se requieren ambos codigos"}), 400

    # Cargar descripciones desde cache
    try:
        sys.path.insert(0, str(Path(__file__).parent / "notebooklm_skill" / "scripts"))
        from cache_utils import cargar_codigos as _get_codigos
        codigos = _get_codigos()
        desc_a  = codigos.get(codigo_a, "")
        desc_b  = codigos.get(codigo_b, "")
    except Exception:
        desc_a = desc_b = ""

    # Análisis comparativo con Claude Haiku
    try:
        from comparador_partidas import comparar_partidas
        analisis = comparar_partidas(query, codigo_a, desc_a, codigo_b, desc_b)
    except Exception as e:
        analisis = {
            "ok": False, "veredicto": "B", "codigo_correcto": codigo_b,
            "pasos": [{"titulo": "Analisis no disponible", "contenido": str(e)}],
            "referencias": [], "conclusion": f"Error en analisis: {e}", "error": str(e)
        }

    # Generar PDF
    try:
        from generador_informe_pdf import generar_informe_pdf
        pdf_bytes = generar_informe_pdf(
            query, codigo_a, desc_a, gravamen_a,
            codigo_b, desc_b, gravamen_b, analisis
        )
        response = make_response(pdf_bytes)
        nombre   = f"Informe_Arancelario_{codigo_a}_vs_{codigo_b}.pdf"
        response.headers["Content-Type"]        = "application/pdf"
        response.headers["Content-Disposition"] = f'attachment; filename="{nombre}"'
        return response
    except Exception as e:
        return jsonify({"error": f"Error generando PDF: {str(e)[:100]}"}), 500


@app.route("/instalar")
def instalar():
    server_url = _get_public_url()
    qr_b64     = _gen_qr_base64(server_url)
    role       = session.get("role", "invitado")
    return render_template("instalar.html", server_url=server_url, qr_b64=qr_b64, role=role)

@app.route("/descargar-app")
def descargar_app():
    server_url = _get_public_url()
    qr_b64     = _gen_qr_base64(server_url)
    html = render_template("app-instalador.html", server_url=server_url, qr_b64=qr_b64)
    resp = make_response(html)
    resp.headers["Content-Type"] = "text/html; charset=utf-8"
    resp.headers["Content-Disposition"] = "attachment; filename=Logistica-Puertos-Aduanas-RD.html"
    return resp

# ── Fichas de descarga por rol (compartir por WhatsApp/correo) ──────────
_ROL_TITULOS = {
    "master":    "Administrador Master",
    "operativo": "Administrador Operativo",
    "invitado":  "Usuario",
}

@app.route("/descargar/<rol>")
def ficha_descarga(rol):
    if rol not in _ROL_TITULOS:
        return redirect(url_for("ficha_descarga", rol="invitado"))
    app_url   = _get_public_url()
    ficha_url = f"{app_url}/descargar/{rol}"
    return render_template("ficha_descarga.html",
                           rol=rol,
                           rol_titulo=_ROL_TITULOS[rol],
                           app_url=app_url,
                           ficha_url=ficha_url)

# ── Aviso profesional al final de cada respuesta ─────────────────────────
_DISCLAIMER = (
    "\n\n---\n"
    "**Nota importante:** Esta respuesta fue generada por inteligencia artificial "
    "a partir de las fuentes cargadas en el sistema. La IA puede cometer errores, "
    "especialmente si los datos de origen no fueron cargados correctamente o están "
    "incompletos. Le recomendamos validar esta información con un especialista en "
    "la materia del producto que desea importar o exportar. Para obtener respuestas "
    "más precisas, solicite a un experto la elaboración de una ficha técnica oficial "
    "de su producto y súbala al sistema utilizando la opción "
    "\"Adjuntar ficha técnica (PDF o JPG)\"."
)

# ── Lógica de consulta: Gemini API (primario) → NotebookLM navegador (fallback) ──
def _parse_subprocess_answer(output, stderr, notebook_id):
    """Extrae la respuesta de texto del stdout de ask_question.py o ask_gemini.py."""
    sep60 = "=" * 60
    sep20 = "=" * 20
    answer = ""

    if sep60 in output:
        parts = output.split(sep60)
        if len(parts) >= 3:
            raw = parts[2]
            cut = raw.find("EXTREMELY IMPORTANT")
            answer = (raw[:cut] if cut != -1 else raw).strip()

    if not answer and sep20 in output:
        parts = [p for p in output.split(sep20) if p.strip()]
        if len(parts) >= 2:
            raw = parts[-1]
            cut = raw.find("EXTREMELY IMPORTANT")
            answer = (raw[:cut] if cut != -1 else raw).strip()

    if not answer and ("=" * 10) in output:
        lines = output.splitlines()
        last_sep = max((i for i, l in enumerate(lines) if "=" * 10 in l), default=-1)
        if last_sep >= 0:
            candidate = "\n".join(lines[last_sep + 1:]).split("EXTREMELY")[0].strip()
            if len(candidate) > 20:
                answer = candidate

    return answer


def _ejecutar_gemini(question, notebook_id, timeout, intento=1):
    """Ejecuta ask_gemini.py como subprocess. Retorna respuesta o None."""
    cmd = [PYTHON, "scripts/ask_gemini.py", "--question", question, "--notebook-id", notebook_id, "--intento", str(intento)]
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONPATH"] = SKILL_DIR
    try:
        result = subprocess.run(
            cmd, cwd=SKILL_DIR,
            capture_output=True, text=True, encoding="utf-8",
            env=env, timeout=timeout
        )
        output = result.stdout or ""
        stderr = result.stderr or ""

        def _safe_print(msg):
            """Print tolerante a emoji/caracteres no-ASCII en stdout piped."""
            try:
                print(msg)
            except UnicodeEncodeError:
                print(msg.encode('ascii', errors='replace').decode('ascii'))

        _safe_print(f"[GEMINI_LOG] rc={result.returncode} stdout_len={len(output)} stderr_len={len(stderr)}")
        _tail = output[-500:] if len(output) > 200 else output
        _safe_print(f"[GEMINI_LOG] stdout={'tail' if len(output) > 200 else 'full'}={_tail}")
        if result.returncode != 0:
            _safe_print(f"[GEMINI_LOG] STDERR: {stderr[-500:]}")
        answer = _parse_subprocess_answer(output, stderr, notebook_id)
        if answer:
            return answer
        _safe_print(f"[GEMINI_NOANS] Sin respuesta. rc={result.returncode} stderr={stderr[-500:]}")
        return None
    except subprocess.TimeoutExpired:
        print(f"[GEMINI_LOG] Timeout en Gemini ({timeout}s)")
        return "TIMEOUT"
    except UnicodeEncodeError as _ue:
        # Este except captura el error de encoding que causaba el 500 original
        try:
            print(f"[GEMINI_LOG] UnicodeEncodeError en logging (encoding issue): {type(_ue).__name__}")
        except Exception:
            pass
        return None
    except Exception as e:
        try:
            print(f"[GEMINI_LOG] Excepcion: {type(e).__name__}")
        except Exception:
            pass
        return None


def _es_respuesta_valida(answer: str, notebook_id: str) -> bool:
    """Gate 2: Valida que Gemini devolvio una respuesta estructurada, no basura.
    Rechaza respuestas vacias, demasiado cortas, o negativas explicitas.
    """
    if not answer or len(answer.strip()) < 60:
        return False
    a_lower = answer.lower()
    # Rechazar negativas/refusals explicitas
    rechazos = [
        "no puedo ayudar", "no tengo informacion", "no tengo suficiente",
        "lo siento, no", "i cannot", "i'm sorry", "no se puede determinar",
        "consulta no valida", "pregunta fuera de scope",
    ]
    if any(r in a_lower for r in rechazos):
        print(f"[VALIDACION] Respuesta rechazada — refusal detectado")
        return False
    # Para nomenclaturas: debe tener estructura arancelaria o intento de clasificacion
    if notebook_id == "biblioteca-de-nomenclaturas":
        tiene_estructura = bool(
            re.search(r'\d{4}[\.\d]*', answer) or                   # codigo numerico
            re.search(r'capitul[oa]\s+\d', answer, re.I) or         # "Capitulo 71"
            re.search(r'partida|subpartida|arancelari', answer, re.I)  # terminologia
        )
        if not tiene_estructura:
            print(f"[VALIDACION] Respuesta rechazada — sin estructura arancelaria ({len(answer)} chars)")
            return False
    return True


def _consultar_cache_fallback(question: str, notebook_id: str) -> "str | None":
    """Gate 3: Busqueda en cache arancelario cuando Gemini no responde.
    Solo para nomenclaturas. Retorna codigos relevantes con gravamenes verificados.
    Fuente: arancel_cache.json (7,616 codigos, pdfplumber 0% IA).
    """
    if notebook_id != "biblioteca-de-nomenclaturas":
        return None

    import unicodedata
    cache_path = os.path.join(
        os.path.dirname(__file__),
        "notebooklm_skill", "data", "fuentes_nomenclatura", "arancel_cache.json"
    )
    if not os.path.exists(cache_path):
        return None

    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            cache = json.load(f)
    except Exception:
        return None

    # Extraer palabras clave de la pregunta (ignorar stopwords)
    stopwords = {
        "cual", "cuál", "es", "el", "la", "los", "las", "de", "del",
        "para", "que", "qué", "un", "una", "como", "código", "codigo",
        "arancelario", "clasificacion", "clasificación", "arancel",
        "me", "puedes", "dar", "dime", "cual", "seria", "sería",
    }

    def _normalizar(txt: str) -> str:
        txt = unicodedata.normalize("NFKD", txt.lower())
        return "".join(c for c in txt if not unicodedata.combining(c))

    pregunta_norm = _normalizar(question)
    palabras = [
        p for p in re.sub(r'[^\w\s]', ' ', pregunta_norm).split()
        if len(p) > 3 and p not in stopwords
    ]

    if not palabras:
        return None

    # Buscar en cache: score por cuantas palabras clave aparecen en la descripcion
    resultados = []
    for codigo, descripcion in cache.items():
        desc_norm = _normalizar(descripcion)
        score = sum(1 for p in palabras if p in desc_norm)
        if score > 0:
            resultados.append((score, codigo, descripcion))

    if not resultados:
        return None

    # Top 5 mas relevantes
    resultados.sort(key=lambda x: x[0], reverse=True)
    top = resultados[:5]

    # Formatear respuesta de fallback
    lineas = [
        "⚠️ RESPUESTA DE EMERGENCIA — CACHE ARANCELARIO VERIFICADO",
        "",
        f"El sistema de IA no pudo procesar tu consulta en este momento.",
        f"Los siguientes códigos del Arancel 7ma Enmienda pueden ser relevantes para:",
        f"  \"{question.strip()}\"",
        "",
        "RESULTADOS DEL CACHE VERIFICADO (pdfplumber, 0% IA):",
        "─" * 50,
    ]
    for score, codigo, descripcion in top:
        # Extraer gravamen del final de la descripcion
        m_grav = re.search(r'\b(\d+)%?\s*$', descripcion.strip())
        grav_str = f" — Gravamen: {m_grav.group(1)}%" if m_grav else ""
        lineas.append(f"  {codigo}: {descripcion.strip()}{grav_str}")

    lineas += [
        "─" * 50,
        "",
        "⚠️ AVISO: Estos resultados son orientativos basados en búsqueda de palabras clave.",
        "Para clasificación oficial, reformule su consulta o intente de nuevo en unos segundos.",
        "Verifique siempre con el Arancel oficial antes de usar en declaraciones aduaneras.",
    ]
    return "\n".join(lineas)


def ask_notebooklm(question, notebook_id, timeout=60):
    """Wrapper de seguridad — siempre retorna string, nunca propaga excepciones.

    Capas de proteccion (para eliminar el error generico en movil):
      1. Intento normal (_ask_notebooklm_internal)
      2. Categorizacion de excepcion (Timeout/Network/API/Otros) para log claro
      3. Fallback a cache arancelario verificado (si notebook de nomenclaturas)
      4. Mensaje final categorizado (nunca generico opaco)
    """
    _tipo_err = None
    _detalle_err = None
    try:
        return _ask_notebooklm_internal(question, notebook_id, timeout)
    except Exception as _e:
        import traceback as _tb
        nombre = type(_e).__name__
        msg = str(_e)
        if "timeout" in msg.lower() or "timed out" in msg.lower() or nombre in ("TimeoutError", "socket.timeout"):
            _tipo_err = "TIMEOUT"
        elif any(k in msg.lower() for k in ("connection", "network", "resolve", "dns")):
            _tipo_err = "RED"
        elif any(k in msg.lower() for k in ("api key", "quota", "429", "403", "permission")):
            _tipo_err = "API"
        elif "json" in msg.lower() or nombre in ("JSONDecodeError", "ValueError"):
            _tipo_err = "FORMATO"
        else:
            _tipo_err = "INTERNO"
        _detalle_err = f"{nombre}: {msg[:200]}"
        print(f"[ASK_FATAL] tipo={_tipo_err} {_detalle_err}")
        print(f"[ASK_FATAL_TRACEBACK]\n{_tb.format_exc()}")

    # ── Capa 3: fallback a cache verificado (solo nomenclaturas) ──
    try:
        fallback = _consultar_cache_fallback(question, notebook_id)
        if fallback:
            print(f"[ASK_FALLBACK_CACHE] Recuperado para notebook={notebook_id} tipo_err={_tipo_err}")
            encabezado = (
                f"[Info: recuperamos tu consulta desde el cache verificado "
                f"porque la IA tuvo un problema temporal ({_tipo_err}).]\n\n"
            )
            return encabezado + fallback
    except Exception as _e2:
        print(f"[ASK_FALLBACK_CACHE_ERROR] {type(_e2).__name__}: {_e2}")

    # ── Capa 4: mensaje categorizado final ──
    mensajes = {
        "TIMEOUT": ("La IA tardó más de lo esperado en responder. "
                    "Intenta de nuevo en unos segundos — si persiste, simplifica la consulta."),
        "RED":     ("Problema temporal de red al conectar con la IA. "
                    "Verifica tu conexión y vuelve a intentar."),
        "API":     ("El servicio de IA reportó un límite temporal (cuota/permiso). "
                    "Vuelve a intentar en 30-60 segundos."),
        "FORMATO": ("La IA devolvió una respuesta con formato inesperado. "
                    "Reformula la pregunta con más detalle del producto."),
        "INTERNO": ("El sistema encontró un error interno procesando tu consulta. "
                    "Intenta de nuevo — si persiste, reporta el error en la app."),
    }
    prefijo = mensajes.get(_tipo_err or "INTERNO", mensajes["INTERNO"])
    return f"{prefijo}\n\n[detalle_tecnico: {_tipo_err} — {_detalle_err}]"


def _ask_notebooklm_internal(question, notebook_id, timeout=60):
    # ── Ruta 1: Gemini API con retry automático + backoff exponencial ──
    gemini_key = os.environ.get("GEMINI_API_KEY", "")
    if gemini_key:
        import time as _time
        import random as _random
        max_intentos = 3
        for intento in range(1, max_intentos + 1):
            print(f"[ASK] Gemini intento {intento}/{max_intentos} — notebook_id={notebook_id} (timeout={timeout}s)")
            answer = _ejecutar_gemini(question, notebook_id, timeout, intento=intento)

            if answer == "TIMEOUT":
                if intento < max_intentos:
                    # Reintentar timeout con backoff (a veces es transitorio)
                    wait = min(2 ** intento + _random.uniform(0, 1), 10)
                    print(f"[ASK] Timeout transitorio — reintentando en {wait:.1f}s...")
                    _time.sleep(wait)
                    continue
                if _IS_CLOUD:
                    return ("El servidor tardó demasiado procesando tu consulta. "
                            "Esto puede ocurrir con imágenes grandes o documentos complejos. "
                            "Por favor intenta de nuevo — la segunda consulta suele ser más rápida.")
                break  # No reintentar timeout, ir a fallback

            if answer and _es_respuesta_valida(answer, notebook_id):
                return answer + _DISCLAIMER
            elif answer:
                # Gemini respondio pero con contenido invalido — reintentar
                print(f"[ASK] Respuesta invalida de Gemini (intento {intento}) — reintentando...")
                answer = None  # Forzar reintento

            # Sin respuesta — reintentar con backoff exponencial + jitter
            if intento < max_intentos:
                wait = min(2 ** intento + _random.uniform(0, 1), 10)
                print(f"[ASK] Sin respuesta — reintentando en {wait:.1f}s (intento {intento + 1})...")
                _time.sleep(wait)

    # ── En cloud: si Gemini no respondió tras retry, error al usuario ──
    if _IS_CLOUD:
        print(f"[ASK] Cloud sin respuesta de Gemini — intentando fallback cache...")
        fallback = _consultar_cache_fallback(question, notebook_id)
        if fallback:
            print(f"[ASK] Fallback cache exitoso — devolviendo resultados verificados")
            return fallback + _DISCLAIMER
        return ("El sistema de IA no pudo procesar tu consulta en este momento. "
                "Intenta reformular tu pregunta de forma más específica "
                "(ej: '¿Cuál es el código arancelario de anillos de oro para joyería?') "
                "y vuelve a consultar. Si el problema persiste, intenta en unos minutos.")

    # ── Ruta 2: NotebookLM con navegador (SOLO local/Windows) ────────────
    print(f"[ASK] Usando NotebookLM (navegador) para notebook_id={notebook_id}")
    cmd = [PYTHON, "scripts/ask_question.py", "--question", question, "--notebook-id", notebook_id]
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONPATH"] = SKILL_DIR
    env.pop("DISPLAY", None)
    if not env.get("PLAYWRIGHT_BROWSERS_PATH"):
        env["PLAYWRIGHT_BROWSERS_PATH"] = "/ms-playwright"

    try:
        result = subprocess.run(
            cmd, cwd=SKILL_DIR,
            capture_output=True, text=True, encoding="utf-8",
            env=env, timeout=1800
        )
    except subprocess.TimeoutExpired:
        return "La consulta tardó demasiado (30 min). Intenta de nuevo con una pregunta más corta."
    except Exception as e:
        return f"Error al ejecutar la consulta: {str(e)[:300]}"

    output = result.stdout or ""
    stderr = result.stderr or ""
    print(f"[ASK_LOG] rc={result.returncode} stdout={output[:300]} stderr={stderr[:300]}")
    if stderr and result.returncode != 0:
        print(f"[ASK_ERROR] rc={result.returncode} stderr={stderr[:800]}")

    answer = _parse_subprocess_answer(output, stderr, notebook_id)

    if not answer:
        diag = stderr[:400] if stderr else "Sin stderr. Verifica cookies y library.json."
        print(f"[ASK_NOANS] stdout={output[:200]} | stderr={diag}")
        return f"No se obtuvo respuesta del cuaderno '{notebook_id}'. El sistema está procesando — intenta de nuevo en 30 segundos."

    return answer + _DISCLAIMER

# ── Migración de datos al iniciar ────────────────────────────────────────
def _migrate_users_admin_to_operativo():
    """Convierte usuarios con tipo='admin' a tipo='operativo' y les asigna
    un password_hash por defecto si no lo tienen."""
    data = load_users()
    changed = False
    for u in data["usuarios"]:
        if u.get("tipo") == "admin":
            u["tipo"] = "operativo"
            if not u.get("password_hash"):
                u["password_hash"] = hashlib.sha256(b"Operativo2024").hexdigest()
            changed = True
    if changed:
        save_users(data)

# Ejecutar migraciones al importar el módulo
_migrate_users_admin_to_operativo()
load_passwords()  # Dispara migración admin→master en passwords.json

# ── Pre-calentamiento: verificar/subir Arancel PDF a Gemini al iniciar ──
def _precalentar_arancel():
    """Verifica o sube el Arancel PDF a Gemini File API en background
    para que la primera consulta no espere el upload (~30s)."""
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        return
    try:
        from google import genai as _genai_w
        from google.genai import types as _types_w
        _client_w = _genai_w.Client(api_key=api_key)
        arancel_cache = os.path.join(SKILL_DIR, "data", "arancel_gemini_cache.json")
        arancel_pdf = os.path.join(SKILL_DIR, "data", "arancel_7ma_enmienda.pdf")

        # Verificar cache existente
        if os.path.exists(arancel_cache):
            try:
                with open(arancel_cache, "r") as f:
                    cached = json.load(f)
                ref = _client_w.files.get(name=cached["name"])
                if ref.state == "ACTIVE":
                    print("[WARMUP] Arancel PDF activo en Gemini — listo")
                    return
            except Exception:
                print("[WARMUP] Cache expirado, re-subiendo...")

        # Subir PDF
        if not os.path.exists(arancel_pdf):
            print(f"[WARMUP] Arancel PDF no encontrado: {arancel_pdf}")
            return

        print("[WARMUP] Subiendo Arancel PDF a Gemini File API...")
        file_ref = _client_w.files.upload(
            file=arancel_pdf,
            config=_types_w.UploadFileConfig(display_name="Arancel 7ma Enmienda RD")
        )
        for _ in range(20):
            file_ref = _client_w.files.get(name=file_ref.name)
            if file_ref.state == "ACTIVE":
                break
            time.sleep(2)

        if file_ref.state == "ACTIVE":
            with open(arancel_cache, "w") as f:
                json.dump({"name": file_ref.name, "uri": file_ref.uri}, f)
            print(f"[WARMUP] Arancel PDF listo: {file_ref.name}")
        else:
            print(f"[WARMUP] Arancel no se proceso: {file_ref.state}")
    except Exception as e:
        print(f"[WARMUP] Error (no critico): {e}")

import threading
threading.Thread(target=_precalentar_arancel, daemon=True).start()

# ══════════════════════════════════════════════════════════════════════════
# MERCEOLOGIA — Endpoints de fichas merceologicas
# Integrado con skill merceologia-producto (triple integracion)
# ══════════════════════════════════════════════════════════════════════════

_MERCEO_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "notebooklm_skill", "data", "merceologia"
)


def _slug_merceo(texto: str) -> str:
    """Slug consistente con el script generar_ficha.py del skill."""
    import unicodedata
    s = (texto or "").strip().lower()
    s = unicodedata.normalize('NFKD', s)
    s = ''.join(c for c in s if not unicodedata.combining(c))
    s = s.replace('ñ', 'n')
    s = re.sub(r'[^a-z0-9]+', '-', s).strip('-')
    return s[:60] or "producto-sin-nombre"


@app.route("/merceologia")
def merceologia_listar():
    """Lista las fichas merceologicas disponibles."""
    if not os.path.isdir(_MERCEO_DIR):
        return jsonify({"fichas": [], "total": 0, "dir": _MERCEO_DIR})
    archivos = sorted([f for f in os.listdir(_MERCEO_DIR) if f.endswith(".md")])
    fichas = []
    for f in archivos:
        ruta = os.path.join(_MERCEO_DIR, f)
        fichas.append({
            "slug": f.replace(".md", ""),
            "archivo": f,
            "tamano_bytes": os.path.getsize(ruta),
            "modificado": os.path.getmtime(ruta),
        })
    return jsonify({"fichas": fichas, "total": len(fichas)})


@app.route("/merceologia/<slug>")
def merceologia_ver(slug):
    """Devuelve el contenido de una ficha merceologica."""
    slug_limpio = _slug_merceo(slug)
    ruta = os.path.join(_MERCEO_DIR, f"{slug_limpio}.md")
    if not os.path.isfile(ruta):
        return jsonify({
            "error": "Ficha no encontrada",
            "slug_buscado": slug_limpio,
            "sugerencia": "Crear con skill merceologia-producto"
        }), 404
    try:
        with open(ruta, "r", encoding="utf-8") as f:
            contenido = f.read()
        return jsonify({
            "slug": slug_limpio,
            "contenido_md": contenido,
            "longitud": len(contenido),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/merceologia/buscar")
def merceologia_buscar():
    """Busca fichas por termino en el contenido."""
    q = request.args.get("q", "").strip().lower()
    if not q or len(q) < 3:
        return jsonify({"error": "Query minima 3 caracteres"}), 400
    if not os.path.isdir(_MERCEO_DIR):
        return jsonify({"hits": []})
    hits = []
    for f in os.listdir(_MERCEO_DIR):
        if not f.endswith(".md"):
            continue
        ruta = os.path.join(_MERCEO_DIR, f)
        try:
            with open(ruta, "r", encoding="utf-8") as fp:
                texto = fp.read().lower()
            if q in texto:
                idx = texto.find(q)
                contexto = texto[max(0, idx-80):idx+len(q)+80]
                hits.append({
                    "slug": f.replace(".md", ""),
                    "contexto": contexto.replace("\n", " ").strip(),
                })
        except Exception:
            pass
    return jsonify({"hits": hits, "total": len(hits), "query": q})


# ── Arranque ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import socket
    local_ip = socket.gethostbyname(socket.gethostname())
    print("\n" + "="*55)
    print("  Logistica de Puertos y Aduanas RD — Servidor")
    print("="*55)
    print(f"\n  URL local:   http://localhost:5000")
    print(f"  URL movil:   http://{local_ip}:5000")
    print(f"\n  [Seguridad] Contrasenas no se muestran en logs.")
    print(f"  [Seguridad] SECRET_KEY: {'env var' if os.environ.get('SECRET_KEY') else 'auto-generada'}")
    print("="*55 + "\n")
    app.run(host="0.0.0.0", port=5000, debug=False)
