"""
Servidor Web - Logistica de Puertos y Aduanas RD
Acceso protegido con contraseña de administrador
"""

import subprocess
import os
import hashlib
import secrets
import json
import uuid
import time
from collections import defaultdict
from datetime import datetime, timedelta
from functools import wraps
from flask import Flask, request, jsonify, render_template, session, redirect, url_for, Response, make_response, send_from_directory

app = Flask(__name__, static_folder='static')

import sys
from pathlib import Path

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
    csp = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "connect-src 'self'; "
        "frame-ancestors 'none';"
    )
    response.headers['Content-Security-Policy'] = csp
    return response

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

# ── Contraseñas por defecto (hash SHA-256) ───────────────────────────────
_DEFAULT_MASTER_HASH = hashlib.sha256(b"DGA2024*").hexdigest()
_DEFAULT_GUEST_HASH = hashlib.sha256(b"Puertos2024").hexdigest()

USERS_FILE       = str(_DATA_DIR / "usuarios.json")
SOLICITUDES_FILE = str(_DATA_DIR / "solicitudes.json")
PASSWORDS_FILE   = str(_DATA_DIR / "passwords.json")
HISTORIAL_FILE   = str(_DATA_DIR / "historial_invitados.json")
RECOVERY_FILE    = str(_DATA_DIR / "recuperaciones.json")
CUADERNOS_FILE   = str(_DATA_DIR / "cuadernos.json")

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
            "pais":       d.get("pais", "").strip(),
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
        pwd_hash = hashlib.sha256(pwd.encode()).hexdigest()
        referer  = request.headers.get("Referer", "")
        from_invitado = role_req == "invitado" and "/invitado" in referer

        # Backward compat: old forms send "admin" → treat as "master"
        if role_req == "admin":
            role_req = "master"

        if role_req == "master" and pwd_hash == get_master_hash():
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
                    elif pwd_hash != user_pw_hash:
                        error = "Contraseña incorrecta. Intenta de nuevo."
                    else:
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

        elif role_req == "invitado" and pwd_hash == get_guest_hash():
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

    # Si hay archivo adjunto, extraer texto / analizar imagen y añadirlo a la pregunta
    producto_identificado = ""
    if archivo:
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

    # Timeout optimizado: 45s texto, 60s imagen (objetivo: respuesta en <30s)
    # Pipeline: Gemini (1 llamada) + cache-first + supervisor Python
    tiene_imagen = bool(producto_identificado) or (archivo is not None)
    timeout_consulta = 60 if tiene_imagen else 45

    try:
        answer = ask_notebooklm(question, notebook_id, timeout=timeout_consulta)
        resp = {"answer": answer}
        if producto_identificado:
            resp["producto_identificado"] = producto_identificado
        return jsonify(resp)
    except subprocess.TimeoutExpired:
        return jsonify({"error": "Tiempo de espera agotado. Intenta de nuevo."}), 504
    except Exception as e:
        print(f"[CONSULTAR_ERROR] {e}")
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
        import google.generativeai as genai
        genai.configure(api_key=api_key)

        # Comprimir imagen automáticamente (2MB → ~200KB, acelera upload)
        compressed_path = _comprimir_imagen(image_path)
        upload_path = compressed_path

        # Subir imagen a Gemini File API
        print(f"[VISION] Subiendo imagen para análisis: {upload_path}")
        img_file = genai.upload_file(upload_path)
        # Esperar a que esté activa
        for _ in range(10):
            status = genai.get_file(img_file.name)
            if status.state.name == "ACTIVE":
                break
            time.sleep(1)

        model = genai.GenerativeModel(
            "gemini-2.0-flash",
            generation_config={"max_output_tokens": 1024}
        )
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
        response = model.generate_content(
            [img_file, prompt],
            request_options={"timeout": 30}
        )
        desc = response.text.strip()
        print(f"[VISION] Producto identificado: {desc[:150]}")

        # Validar que Vision no pidio mas info ni se nego a identificar
        _rechazos = ["no puedo identificar", "necesito que", "proporcione",
                     "describa el producto", "no me permite identificar",
                     "no es posible determinar"]
        if any(r in desc.lower() for r in _rechazos):
            print("[VISION] Vision intento rechazar — forzando re-identificacion")
            response2 = model.generate_content(
                [img_file, "Describe el objeto fisico visible en esta imagen. "
                 "Responde: PRODUCTO: [que es] MATERIAL: [de que esta hecho] "
                 "FUNCION: [para que sirve] DESCRIPCION: [descripcion tecnica breve]"],
                request_options={"timeout": 20}
            )
            desc = response2.text.strip()
            print(f"[VISION] Re-identificacion: {desc[:150]}")

        # Limpiar archivo subido en Gemini
        try:
            genai.delete_file(img_file.name)
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
            nuevo["password_hash"]      = hashlib.sha256(pw_raw.encode()).hexdigest()
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

    actual_hash = hashlib.sha256(actual.encode()).hexdigest() if actual else ""
    nueva_hash  = hashlib.sha256(nueva.encode()).hexdigest()
    passwords   = load_passwords()

    correo_session = session.get("correo", "")
    nombre_session = session.get("nombre", "")

    # ── Cambiar contraseña maestra (solo master) ──
    if tipoPassCambiar in ("admin", "master"):
        if role != "master":
            return jsonify({"error": "Solo el master puede cambiar esta contraseña."}), 403
        if actual_hash != passwords.get("master", _DEFAULT_MASTER_HASH):
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
            if actual_hash != usuario.get("password_hash", ""):
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
                if actual_hash != passwords.get("invitado", _DEFAULT_GUEST_HASH):
                    return jsonify({"error": "La contraseña actual es incorrecta."}), 400
            passwords["invitado"] = nueva_hash
            save_passwords(passwords)
            # Marcar que ya cambio la contrasena
            data = load_users()
            for u in data["usuarios"]:
                if u["correo"].lower() == correo_session.lower():
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


def ask_notebooklm(question, notebook_id, timeout=45):
    # ── Ruta 1: Gemini API (sin restricción de IP, sin navegador) ────────
    gemini_key = os.environ.get("GEMINI_API_KEY", "")
    if gemini_key:
        print(f"[ASK] Usando Gemini API para notebook_id={notebook_id} (timeout={timeout}s)")
        cmd = [PYTHON, "scripts/ask_gemini.py", "--question", question, "--notebook-id", notebook_id]
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
            print(f"[GEMINI_LOG] rc={result.returncode} stdout_len={len(output)} stderr_len={len(stderr)}")
            print(f"[GEMINI_LOG] stdout_tail={output[-500:]}" if len(output) > 200 else f"[GEMINI_LOG] stdout={output}")
            if result.returncode != 0:
                print(f"[GEMINI_LOG] STDERR: {stderr[-500:]}")
            answer = _parse_subprocess_answer(output, stderr, notebook_id)
            if answer:
                return answer + _DISCLAIMER
            print(f"[GEMINI_NOANS] Sin respuesta. rc={result.returncode} stderr={stderr[-500:]}")
        except subprocess.TimeoutExpired:
            print(f"[GEMINI_LOG] Timeout en Gemini ({timeout}s)")
            # En cloud: devolver error inmediato (NotebookLM browser no funciona)
            if _IS_CLOUD:
                return ("El servidor tardó demasiado procesando tu consulta. "
                        "Esto puede ocurrir con imágenes grandes o documentos complejos. "
                        "Por favor intenta de nuevo — la segunda consulta suele ser más rápida.")
        except Exception as e:
            print(f"[GEMINI_LOG] Excepción: {e}")

    # ── En cloud: si Gemini no respondió, NO intentar NotebookLM (no funciona) ─
    if _IS_CLOUD:
        print("[ASK] Cloud sin respuesta de Gemini — retornando error al usuario")
        return ("No se pudo obtener respuesta del sistema de IA. "
                "Verifica que tu consulta sea clara y concisa, e intenta de nuevo en unos segundos.")

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
