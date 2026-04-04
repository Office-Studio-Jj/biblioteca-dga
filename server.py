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
from datetime import datetime
from functools import wraps
from flask import Flask, request, jsonify, render_template, session, redirect, url_for, Response, make_response

app = Flask(__name__, static_folder='static')
app.secret_key = secrets.token_hex(32)   # clave de sesion aleatoria por arranque

# ── Contraseñas por defecto (hash SHA-256) ───────────────────────────────
_DEFAULT_ADMIN_HASH = hashlib.sha256(b"DGA2024*").hexdigest()
_DEFAULT_GUEST_HASH = hashlib.sha256(b"Puertos2024").hexdigest()

import sys
from pathlib import Path

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
USERS_FILE       = str(_DATA_DIR / "usuarios.json")
SOLICITUDES_FILE = str(_DATA_DIR / "solicitudes.json")
PASSWORDS_FILE   = str(_DATA_DIR / "passwords.json")
HISTORIAL_FILE   = str(_DATA_DIR / "historial_invitados.json")

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
            return json.load(f)
    except Exception:
        return {"admin": _DEFAULT_ADMIN_HASH, "invitado": _DEFAULT_GUEST_HASH}

def save_passwords(data):
    with open(PASSWORDS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_admin_hash():
    return load_passwords().get("admin", _DEFAULT_ADMIN_HASH)

def get_guest_hash():
    return load_passwords().get("invitado", _DEFAULT_GUEST_HASH)

# ── Correos oficiales del sistema ────────────────────────────────────────
DISTRIBUTION_EMAIL = "consultoria.puertos.aduanas@gmail.com"   # envia la app
SUPPORT_EMAIL      = "consulta.puertos.aduanas@gmail.com"      # recibe solicitudes
WHATSAPP_ADMIN     = "18093547636"                              # WhatsApp admin

NOTEBOOKS = [
    {"id": "biblioteca-de-nomenclaturas",                        "nombre": "Nomenclaturas",          "emoji": "📋"},
    {"id": "biblioteca-legal-y-procedimiento-dga",               "nombre": "Legal y Procedimientos", "emoji": "⚖️"},
    {"id": "biblioteca-para-valoracion-dga",                     "nombre": "Valoracion",             "emoji": "💰"},
    {"id": "biblioteca-guia-integral-de-regimenes-y-subastas",   "nombre": "Regimenes y Subastas",   "emoji": "📦"},
    {"id": "biblioteca-para-aforo-dga",                          "nombre": "Aforo DGA",              "emoji": "🔍"},
    {"id": "biblioteca-procedimiento-vucerd",                    "nombre": "VUCERD",                 "emoji": "🪟"},
    {"id": "biblioteca-de-normas-y-origen-dga",                  "nombre": "Normas y Origen",        "emoji": "🌐"},
]

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

# ── Decorador de protección ─────────────────────────────────────────────
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in") or session.get("role") != "admin":
            return jsonify({"error": "Acceso denegado"}), 403
        return f(*args, **kwargs)
    return decorated

# ── Registro ────────────────────────────────────────────────────────────
@app.route("/registro", methods=["GET", "POST"])
def registro():
    if request.method == "POST":
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
    if request.method == "POST":
        pwd      = request.form.get("password", "")
        role_req = request.form.get("role", "admin")
        correo   = request.form.get("correo", "").strip().lower()
        pwd_hash = hashlib.sha256(pwd.encode()).hexdigest()

        if role_req == "admin" and pwd_hash == get_admin_hash():
            # Admins creados en el panel usan su correo + contraseña admin
            if correo:
                usuario = find_user_by_email(correo)
                if usuario and usuario.get("tipo") == "admin" and not usuario.get("bloqueado"):
                    session["logged_in"] = True
                    session["role"]      = "admin"
                    session["correo"]    = correo
                    session["nombre"]    = usuario["nombre"]
                    return redirect(url_for("index"))
                elif usuario and usuario.get("bloqueado"):
                    error = "Tu acceso ha sido bloqueado por el administrador."
                elif usuario:
                    error = "Este correo no tiene permisos de administrador."
                else:
                    error = "Correo no encontrado. Ingresa sin correo para acceso maestro."
            else:
                # Admin maestro original (sin correo)
                session["logged_in"] = True
                session["role"]      = "admin"
                session["correo"]    = "admin"
                session["nombre"]    = "Administrador"
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
                    session["logged_in"]          = True
                    session["role"]               = "invitado"
                    session["correo"]             = correo
                    session["nombre"]             = usuario["nombre"]
                    session["must_change_password"] = primer_acceso
                    evento = "primer_acceso" if primer_acceso else "inicio_sesion"
                    log_historial(correo, usuario["nombre"], evento,
                                  "Primer acceso — debe cambiar contraseña" if primer_acceso else "Inicio de sesión")
                    return redirect(url_for("index"))
        else:
            error = "Contraseña incorrecta. Intenta de nuevo."

    return render_template("login.html", error=error)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# ── App principal (protegida) ────────────────────────────────────────────
@app.route("/")
@login_required
def index():
    role                = session.get("role", "invitado")
    nombre              = session.get("nombre", "")
    must_change_password = session.get("must_change_password", False)
    return render_template("index.html", notebooks=NOTEBOOKS, role=role, nombre=nombre,
                           must_change_password=must_change_password)

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

    if not question:
        return jsonify({"error": "Escribe una pregunta"}), 400
    if not notebook_id:
        return jsonify({"error": "Selecciona un cuaderno"}), 400

    # Si hay archivo adjunto, extraer texto y añadirlo a la pregunta
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
                question = question + "\n\n[Ficha técnica adjunta]:\n" + texto_archivo[:3000]
        except Exception as ex:
            pass  # Si falla la extracción, continúa solo con la pregunta

    try:
        answer = ask_notebooklm(question, notebook_id)
        return jsonify({"answer": answer})
    except subprocess.TimeoutExpired:
        return jsonify({"error": "Tiempo de espera agotado (30 min). Intenta de nuevo."}), 504
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def _extraer_texto_archivo(path, ext):
    """Extrae texto de PDF o imagen para incluir en la consulta."""
    try:
        if ext == ".pdf":
            # Intentar con PyPDF2 o pdfplumber
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
            return "[PDF adjunto — no se pudo extraer texto. Instala pdfplumber: pip install pdfplumber]"
        elif ext in (".jpg", ".jpeg", ".png"):
            # Intentar OCR con pytesseract
            try:
                from PIL import Image
                import pytesseract
                img = Image.open(path)
                return pytesseract.image_to_string(img, lang="spa+eng").strip()
            except ImportError:
                pass
            return "[Imagen adjunta — no se pudo extraer texto. Instala pytesseract para OCR]"
    except Exception as e:
        return f"[Error al leer archivo: {e}]"
    return ""

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
    if not correo or correo == "admin":
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
@admin_required
def admin_solicitudes():
    return jsonify(load_solicitudes())

@app.route("/admin/solicitudes/marcar", methods=["POST"])
@admin_required
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
@admin_required
def admin_usuarios():
    data = load_users()
    return jsonify(data)

@app.route("/admin/bloquear", methods=["POST"])
@admin_required
def admin_bloquear():
    uid    = request.json.get("id", "")
    estado = request.json.get("bloqueado", True)
    data   = load_users()
    for u in data["usuarios"]:
        if u["id"] == uid:
            u["bloqueado"] = estado
            save_users(data)
            accion = "bloqueado" if estado else "desbloqueado"
            return jsonify({"ok": True, "mensaje": f"Usuario {accion}."})
    return jsonify({"error": "Usuario no encontrado"}), 404

@app.route("/admin/usuarios/crear", methods=["POST"])
@admin_required
def admin_crear_usuario():
    d      = request.json or {}
    correo = d.get("correo", "").strip().lower()
    tipo   = d.get("tipo", "invitado")   # "invitado" o "admin"
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
    data = load_users()
    data["usuarios"].append(nuevo)
    save_users(data)
    return jsonify({"ok": True, "mensaje": f"Usuario {nuevo['nombre']} creado como {tipo}."})

@app.route("/admin/usuarios/editar", methods=["POST"])
@admin_required
def admin_editar_usuario():
    d   = request.json or {}
    uid = d.get("id", "")
    data = load_users()
    for u in data["usuarios"]:
        if u["id"] == uid:
            campos = ["nombre","correo","whatsapp","profesion","dedicacion",
                      "pais","provincia","municipio","calle","numero","tipo"]
            for c in campos:
                if c in d:
                    u[c] = d[c].strip() if isinstance(d[c], str) else d[c]
            save_users(data)
            return jsonify({"ok": True})
    return jsonify({"error": "Usuario no encontrado"}), 404

@app.route("/admin/usuarios/eliminar", methods=["POST"])
@admin_required
def admin_eliminar_usuario():
    uid  = (request.json or {}).get("id", "")
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
    d            = request.json or {}
    tipo         = d.get("tipo", "")          # "admin" o "invitado"
    actual       = d.get("actual", "")
    nueva        = d.get("nueva", "")
    confirmacion = d.get("confirmacion", "")
    role         = session.get("role", "")

    if not actual or not nueva or not confirmacion:
        return jsonify({"error": "Todos los campos son obligatorios."}), 400
    if nueva != confirmacion:
        return jsonify({"error": "La nueva contraseña y la confirmación no coinciden."}), 400
    if len(nueva) < 6:
        return jsonify({"error": "La contraseña debe tener al menos 6 caracteres."}), 400

    actual_hash = hashlib.sha256(actual.encode()).hexdigest()
    nueva_hash  = hashlib.sha256(nueva.encode()).hexdigest()
    passwords   = load_passwords()

    correo_session = session.get("correo", "")
    nombre_session = session.get("nombre", "")

    if tipo == "admin":
        if role != "admin":
            return jsonify({"error": "Solo el administrador puede cambiar esta contraseña."}), 403
        if actual_hash != passwords.get("admin", _DEFAULT_ADMIN_HASH):
            return jsonify({"error": "La contraseña actual es incorrecta."}), 400
        passwords["admin"] = nueva_hash
        save_passwords(passwords)
        log_historial(correo_session, nombre_session, "cambio_contrasena", "Cambió la contraseña de administrador")
        return jsonify({"ok": True, "mensaje": "Contraseña de administrador actualizada correctamente."})

    elif tipo == "invitado":
        if role == "admin":
            # Admin puede cambiar la clave de invitado sin verificar la actual
            passwords["invitado"] = nueva_hash
            save_passwords(passwords)
            log_historial(correo_session, nombre_session, "cambio_contrasena", "Admin cambió la contraseña de invitados")
            return jsonify({"ok": True, "mensaje": "Contraseña de invitado actualizada correctamente."})
        elif role == "invitado":
            if actual_hash != passwords.get("invitado", _DEFAULT_GUEST_HASH):
                return jsonify({"error": "La contraseña actual es incorrecta."}), 400
            passwords["invitado"] = nueva_hash
            save_passwords(passwords)
            # Marcar que ya cambió la contraseña
            data = load_users()
            for u in data["usuarios"]:
                if u["correo"].lower() == correo_session.lower():
                    u["password_changed"] = True
                    break
            save_users(data)
            session["must_change_password"] = False
            log_historial(correo_session, nombre_session, "cambio_contrasena", "Cambió su contraseña por primera vez")
            return jsonify({"ok": True, "mensaje": "Contraseña actualizada correctamente."})
        else:
            return jsonify({"error": "Acceso denegado."}), 403
    else:
        return jsonify({"error": "Tipo de contraseña no válido."}), 400


@app.route("/admin/historial")
@admin_required
def admin_historial():
    return jsonify(load_historial())

@app.route("/admin/historial/eliminar", methods=["POST"])
@admin_required
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
@admin_required
def admin_historial_limpiar():
    save_historial({"registros": []})
    return jsonify({"ok": True})


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
    if session.get("role") != "admin":
        return jsonify({"error": "Solo el administrador puede editar."}), 403
    contenido = request.json.get("contenido", "")
    try:
        with open(GUIA_FILE, "w", encoding="utf-8") as f:
            f.write(contenido)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ── Instalador / Descarga App ────────────────────────────────────────────
# URL pública ngrok (se detecta automáticamente si está activo)
def _get_public_url():
    """Devuelve la URL pública de ngrok si está activo, o la IP local."""
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

# ── Lógica NotebookLM ────────────────────────────────────────────────────
def ask_notebooklm(question, notebook_id):
    cmd = [PYTHON, "scripts/ask_question.py", "--question", question, "--notebook-id", notebook_id]
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    result = subprocess.run(cmd, cwd=SKILL_DIR, capture_output=True, text=True, encoding="utf-8", env=env, timeout=1800)
    output = result.stdout
    sep = "=" * 20
    parts = [p for p in output.split(sep) if p.strip()]
    answer = ""
    if len(parts) >= 3:
        raw = parts[2]
        cut = raw.find("EXTREMELY IMPORTANT")
        if cut != -1:
            raw = raw[:cut]
        answer = raw.strip()
    if not answer and result.returncode == 0:
        lines = output.splitlines()
        idx = max((i for i, l in enumerate(lines) if "=" * 20 in l), default=-1)
        if idx >= 0:
            answer = "\n".join(lines[idx+1:]).split("EXTREMELY")[0].strip()
    if not answer:
        err = result.stderr.strip()
        answer = f"No se obtuvo respuesta.{' Error: ' + err[:200] if err else ' Verifica que el cuaderno tenga fuentes cargadas.'}"
    return answer

# ── Arranque ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import socket
    local_ip = socket.gethostbyname(socket.gethostname())
    print("\n" + "="*55)
    print("  Logistica de Puertos y Aduanas RD — Servidor")
    print("="*55)
    print(f"\n  URL local:   http://localhost:5000")
    print(f"  URL movil:   http://{local_ip}:5000")
    print(f"\n  Contrasena admin:    DGA2024*")
    print(f"  Contrasena invitado: Puertos2024")
    print("="*55 + "\n")
    app.run(host="0.0.0.0", port=5000, debug=False)
