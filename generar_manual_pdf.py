"""
Genera manuales PDF profesionales para Admin e Invitado.
Uso:  python generar_manual_pdf.py [admin|invitado|ambos] [ruta_salida]
"""
import sys, os
from fpdf import FPDF

# ── Configuración ──────────────────────────────────────────────────────
TITULO_APP  = "Logistica de Puertos y Aduanas RD"
SUBTITULO   = "Direccion General de Aduanas - Republica Dominicana"
URL_APP     = "https://biblioteca-dga-production.up.railway.app"  # ← Actualizar aquí si cambia el dominio Railway

COLOR_NAVY   = (15, 23, 42)
COLOR_GOLD   = (212, 175, 55)
COLOR_BLUE   = (59, 130, 246)
COLOR_WHITE  = (255, 255, 255)
COLOR_GRAY   = (148, 163, 184)
COLOR_DARK   = (30, 41, 59)
COLOR_GREEN  = (74, 222, 128)
COLOR_YELLOW = (251, 191, 36)

# ── Contenido Admin ────────────────────────────────────────────────────
SECCIONES_ADMIN = [
    {
        "titulo": "Iniciar sesion como administrador",
        "sub": "Acceso al sistema completo",
        "pasos": [
            "Abre la app en tu dispositivo o en " + URL_APP.replace("https://", ""),
            "Selecciona el rol Administrador (corona dorada)",
            "Si eres el administrador maestro: deja el correo vacio e ingresa la contrasena maestra",
            "Si eres un admin creado en el panel: ingresa tu correo y la contrasena de administrador",
            "Haz clic en 'Ingresar'",
        ],
        "nota": "La contrasena maestra por defecto es DGA2024*. Cambiala despues del primer uso.",
        "nota_tipo": "aviso",
    },
    {
        "titulo": "Realizar consultas a los cuadernos DGA",
        "sub": "Busqueda inteligente por cuaderno",
        "pasos": [
            "En la pantalla principal, selecciona el cuaderno correspondiente (Nomenclaturas, Legal, Valoracion, etc.)",
            "Escribe tu consulta en el campo 'Escribe tu consulta'",
            "Opcionalmente adjunta una ficha tecnica en PDF o JPG",
            "Haz clic en 'Consultar' y espera la respuesta (puede tardar hasta 30 minutos)",
        ],
        "nota": "Cada cuaderno esta especializado en un area distinta de la DGA. Selecciona el mas adecuado.",
        "nota_tipo": "info",
    },
    {
        "titulo": "Adjuntar ficha tecnica",
        "sub": "PDF o imagen JPG/PNG",
        "pasos": [
            "En el area de consulta, toca 'Adjuntar ficha tecnica (PDF o JPG) - opcional'",
            "Selecciona el archivo desde tu dispositivo",
            "El nombre del archivo aparecera confirmado. Si deseas quitarlo, toca 'Quitar archivo'",
            "Escribe tu consulta y envia. El sistema extrae el texto del archivo automaticamente",
        ],
        "nota": "El sistema extrae automaticamente el texto del PDF para enriquecer la consulta.",
        "nota_tipo": "info",
    },
    {
        "titulo": "Gestionar usuarios e invitados",
        "sub": "Panel de administracion",
        "pasos": [
            "En la pantalla principal, toca la pestana 'Admin' (corona dorada, parte inferior)",
            "Veras la lista completa de todos los usuarios registrados",
            "Cada usuario muestra: nombre, correo, tipo, estado y opciones de accion",
            "Usa la barra de busqueda para filtrar usuarios rapidamente",
        ],
        "nota": "Solo el administrador puede ver y gestionar esta seccion.",
        "nota_tipo": "ok",
    },
    {
        "titulo": "Crear nuevo usuario",
        "sub": "Invitado o administrador",
        "pasos": [
            "En la seccion de usuarios (tab Admin), toca el boton 'Crear'",
            "Completa el formulario: nombre, correo, WhatsApp, profesion, pais, etc.",
            "En 'Tipo' selecciona 'invitado' o 'admin'",
            "Haz clic en 'Guardar'",
        ],
        "nota": "Los usuarios creados como admin acceden con su correo + la contrasena maestra.",
        "nota_tipo": "aviso",
    },
    {
        "titulo": "Editar y eliminar usuarios",
        "sub": "Modificar o borrar registros",
        "pasos": [
            "En la lista de usuarios, localiza el usuario deseado",
            "Toca el icono 'Editar' para modificar sus datos, luego guarda",
            "Toca el icono 'Eliminar' para borrar permanentemente el usuario",
        ],
        "nota": "La eliminacion es permanente. El usuario no podra recuperar su acceso.",
        "nota_tipo": "aviso",
    },
    {
        "titulo": "Bloquear y desbloquear usuarios",
        "sub": "Control de acceso temporal",
        "pasos": [
            "En la lista de usuarios, localiza el usuario",
            "Toca 'Bloquear' para impedir su acceso sin eliminar su cuenta",
            "Para restaurar el acceso, toca 'Desbloquear'",
        ],
        "nota": "Un usuario bloqueado ve el mensaje 'Tu acceso ha sido bloqueado' al intentar ingresar.",
        "nota_tipo": "info",
    },
    {
        "titulo": "Cambiar contrasena",
        "sub": "Admin puede cambiar cualquier contrasena",
        "pasos": [
            "Toca tu perfil (nombre arriba) y luego el boton 'Cambiar clave'",
            "Selecciona si deseas cambiar la contrasena de Administrador o de Invitado",
            "Ingresa la contrasena actual, la nueva y confirma la nueva",
            "Haz clic en 'Guardar'",
        ],
        "nota": "Al cambiar la contrasena de invitado, todos los invitados deberan usar la nueva clave.",
        "nota_tipo": "aviso",
    },
    {
        "titulo": "Recuperacion de contrasena",
        "sub": "Gestionar solicitudes de recuperacion",
        "pasos": [
            "Cuando un usuario olvida su contrasena, genera una solicitud desde la pantalla de login",
            "En la pestana 'Info', ve a la seccion 'Recuperaciones de Contrasena'",
            "Veras la solicitud con el codigo de 6 digitos generado automaticamente",
            "Toca 'WhatsApp' o 'Correo' para enviar el codigo al usuario",
            "El usuario ingresa el codigo en la pagina de recuperacion y establece su nueva contrasena",
        ],
        "nota": "El codigo se invalida automaticamente una vez usado.",
        "nota_tipo": "ok",
    },
    {
        "titulo": "Historial de invitados",
        "sub": "Registro completo de actividad",
        "pasos": [
            "En la pestana 'Info', desplazate a la seccion 'Historial de Invitados'",
            "Veras todos los eventos: registros, inicios de sesion, cambios de contrasena",
            "Para eliminar un registro individual, toca el icono de eliminar junto al registro",
            "Para limpiar todo el historial, toca 'Limpiar' en el encabezado de la seccion",
        ],
        "nota": "Esta seccion es completamente invisible para los invitados.",
        "nota_tipo": "ok",
    },
    {
        "titulo": "Gestion dinamica de cuadernos",
        "sub": "Agregar, editar, eliminar y reordenar cuadernos",
        "pasos": [
            "En la pestana 'Admin', desplazate a la seccion 'Mis Cuadernos NotebookLM'",
            "Toca 'Nuevo Cuaderno' para agregar un cuaderno con nombre, emoji y URL",
            "Toca 'Editar' en cualquier cuaderno para modificar sus datos",
            "Toca 'Eliminar' para quitar un cuaderno de la lista",
            "Arrastra los cuadernos para cambiar su orden de aparicion",
        ],
        "nota": "Los cambios se reflejan inmediatamente para todos los usuarios.",
        "nota_tipo": "ok",
    },
    {
        "titulo": "Compartir e instalar la app",
        "sub": "Distribucion a nuevos usuarios",
        "pasos": [
            "En la pantalla principal, toca la pestana 'Instalar'",
            "Veras el codigo QR de acceso y la URL publica de la app",
            "Comparte por WhatsApp o Correo usando los botones disponibles",
            "El nuevo usuario escanea el QR o abre la URL, se registra y accede",
        ],
        "nota": "Solo el administrador puede ver el QR, la URL y los botones de compartir.",
        "nota_tipo": "info",
    },
    {
        "titulo": "Acceso desde la nube (Railway)",
        "sub": "Disponible 24/7 aunque el PC este apagado",
        "pasos": [
            "La app esta alojada en Railway y disponible siempre en: " + URL_APP.replace("https://", ""),
            "Al encender tu PC, se sincroniza automaticamente con los ultimos cambios de la nube",
            "El backup local se actualiza automaticamente en el disco externo D:\\BIBLIOTECA-DGA-APP",
        ],
        "nota": "3 niveles de respaldo: Nube (Railway) > Disco externo (D:) > PC local.",
        "nota_tipo": "ok",
    },
]

# ── Contenido Invitado ─────────────────────────────────────────────────
SECCIONES_INVITADO = [
    {
        "titulo": "Registrarse por primera vez",
        "sub": "Crear tu cuenta de invitado",
        "pasos": [
            "En la pantalla de login, toca 'Primera vez? Registrate aqui'",
            "Completa el formulario: nombre, correo, WhatsApp, profesion, pais y direccion",
            "Toca 'Registrarse'. Seras redirigido automaticamente a la app",
            "En tu primer acceso, el sistema te pedira cambiar tu contrasena obligatoriamente",
        ],
        "nota": "El correo es tu identificador unico. No lo compartas con otros usuarios.",
        "nota_tipo": "aviso",
    },
    {
        "titulo": "Iniciar sesion como invitado",
        "sub": "Acceso a tus consultas",
        "pasos": [
            "Abre la app y selecciona el rol 'Invitado'",
            "Ingresa tu correo registrado",
            "Ingresa tu contrasena (la que estableciste al registrarte o en tu ultimo cambio)",
            "Toca 'Ingresar'",
        ],
        "nota": "Si olvidaste tu contrasena, usa la opcion 'Olvidaste tu contrasena?' en la pantalla de login.",
        "nota_tipo": "info",
    },
    {
        "titulo": "Cambio obligatorio de contrasena",
        "sub": "Solo en el primer acceso",
        "pasos": [
            "Al ingresar por primera vez, se abre automaticamente el formulario de cambio de contrasena",
            "En 'Contrasena actual' ingresa: Puertos2024 (clave por defecto)",
            "Escribe tu nueva contrasena (minimo 6 caracteres) y confirmala",
            "Toca 'Guardar'. A partir de ese momento usaras tu nueva contrasena",
        ],
        "nota": "No podras acceder a la app hasta completar este paso. Es obligatorio por seguridad.",
        "nota_tipo": "aviso",
    },
    {
        "titulo": "Realizar una consulta al cuaderno DGA",
        "sub": "Busqueda inteligente",
        "pasos": [
            "En la pantalla principal, selecciona el cuaderno que necesitas (Nomenclaturas, Legal, Valoracion, etc.)",
            "Redacta tu pregunta con el mayor detalle posible",
            "Toca el boton 'Consultar'",
            "Espera la respuesta. Puede tardar entre 1 y 30 minutos segun la complejidad",
        ],
        "nota": "Cuanto mas detallada sea tu pregunta, mas precisa sera la respuesta.",
        "nota_tipo": "ok",
    },
    {
        "titulo": "Adjuntar ficha tecnica",
        "sub": "PDF o imagen JPG/PNG opcional",
        "pasos": [
            "Debajo del campo de consulta, toca 'Adjuntar ficha tecnica (PDF o JPG) - opcional'",
            "Selecciona el archivo desde tu dispositivo (maximo recomendado: 5 paginas)",
            "El nombre del archivo aparecera en verde cuando este listo",
            "Si deseas quitarlo, toca 'Quitar archivo' y luego envia tu consulta normalmente",
        ],
        "nota": "El sistema extrae el texto del documento y lo incluye automaticamente en tu consulta.",
        "nota_tipo": "info",
    },
    {
        "titulo": "Cambiar tu contrasena",
        "sub": "En cualquier momento",
        "pasos": [
            "En la pantalla principal, toca tu nombre en la parte superior para ver tu perfil",
            "Toca el boton 'Cambiar clave'",
            "Ingresa tu contrasena actual, luego la nueva contrasena y confirmala",
            "Toca 'Guardar'",
        ],
        "nota": "Recuerda guardar tu nueva contrasena en un lugar seguro.",
        "nota_tipo": "aviso",
    },
    {
        "titulo": "Recuperar contrasena olvidada",
        "sub": "Solicitar codigo al administrador",
        "pasos": [
            "En la pantalla de login, toca 'Olvidaste tu contrasena? Recuperala aqui'",
            "Selecciona el rol 'Invitado' e ingresa tu correo registrado",
            "Toca 'Solicitar codigo'",
            "Toca 'Notificar al Admin por WhatsApp' para avisarle que necesitas el codigo",
            "Una vez que el admin te envie el codigo de 6 digitos, toca 'Ya tengo mi codigo'",
            "Ingresa tu correo, el codigo recibido y tu nueva contrasena. Toca 'Cambiar contrasena'",
        ],
        "nota": "Seras redirigido al login automaticamente al completar el proceso.",
        "nota_tipo": "ok",
    },
    {
        "titulo": "Instalar la app en tu celular",
        "sub": "Acceso rapido desde la pantalla de inicio",
        "pasos": [
            "Abre Chrome en tu celular y visita la URL que te compartio el administrador",
            "Toca los 3 puntos (menu de Chrome) en la esquina superior derecha",
            "Selecciona 'Anadir a pantalla de inicio'",
            "Confirma el nombre y toca 'Anadir'. El icono aparecera en tu pantalla de inicio",
        ],
        "nota": "Si tu Samsung bloquea la instalacion: ve a Ajustes > Pantalla de inicio > desactiva 'Bloquear diseno'.",
        "nota_tipo": "info",
    },
    {
        "titulo": "Solicitar acceso al administrador",
        "sub": "Para casos que requieren ayuda",
        "pasos": [
            "Si necesitas ayuda, ve a la pestana 'Info'",
            "Toca el boton 'Enviar solicitud al Admin'",
            "Completa el formulario: nombre, WhatsApp, correo, situacion y accion requerida",
            "Elige enviar por WhatsApp o Correo",
        ],
        "nota": "El administrador recibira tu solicitud y te contactara a la brevedad.",
        "nota_tipo": "ok",
    },
    {
        "titulo": "Cerrar sesion",
        "sub": "Salir de forma segura",
        "pasos": [
            "Toca tu nombre en la parte superior de la pantalla para abrir tu perfil",
            "Toca el boton 'Cerrar sesion'",
            "Seras redirigido a la pantalla de login",
        ],
        "nota": "Por seguridad, cierra siempre la sesion si usas un dispositivo compartido.",
        "nota_tipo": "aviso",
    },
]


class ManualPDF(FPDF):
    def __init__(self, rol, color_accent):
        super().__init__()
        self.rol = rol
        self.color_accent = color_accent
        self.set_auto_page_break(auto=True, margin=25)

    # ── Header ──
    def header(self):
        if self.page_no() == 1:
            return  # portada personalizada
        self.set_font("Helvetica", "B", 8)
        self.set_text_color(*COLOR_GRAY)
        titulo_rol = "Manual del Administrador" if self.rol == "admin" else "Manual del Invitado"
        self.cell(0, 8, f"{TITULO_APP}  |  {titulo_rol}", align="C")
        self.ln(4)
        # línea dorada
        self.set_draw_color(*self.color_accent)
        self.set_line_width(0.5)
        self.line(15, self.get_y(), self.w - 15, self.get_y())
        self.ln(6)

    # ── Footer ──
    def footer(self):
        self.set_y(-18)
        self.set_draw_color(*COLOR_GRAY)
        self.set_line_width(0.2)
        self.line(15, self.get_y(), self.w - 15, self.get_y())
        self.ln(3)
        self.set_font("Helvetica", "", 7)
        self.set_text_color(*COLOR_GRAY)
        self.cell(0, 6, f"Pagina {self.page_no()} / {{nb}}", align="C")

    # ── Portada ──
    def portada(self):
        self.add_page()
        self.ln(45)
        # Título app
        self.set_font("Helvetica", "B", 26)
        self.set_text_color(*self.color_accent)
        self.cell(0, 14, TITULO_APP, align="C", new_x="LMARGIN", new_y="NEXT")
        self.ln(4)
        self.set_font("Helvetica", "", 12)
        self.set_text_color(*COLOR_GRAY)
        self.cell(0, 8, SUBTITULO, align="C", new_x="LMARGIN", new_y="NEXT")
        self.ln(18)
        # Línea decorativa
        self.set_draw_color(*self.color_accent)
        self.set_line_width(1)
        cx = self.w / 2
        self.line(cx - 40, self.get_y(), cx + 40, self.get_y())
        self.ln(18)
        # Título manual
        self.set_font("Helvetica", "B", 22)
        self.set_text_color(255, 255, 255) if self.rol == "admin" else None
        self.set_text_color(*self.color_accent)
        titulo_manual = "Manual del Administrador" if self.rol == "admin" else "Manual del Invitado"
        self.cell(0, 12, titulo_manual, align="C", new_x="LMARGIN", new_y="NEXT")
        self.ln(6)
        self.set_font("Helvetica", "", 11)
        self.set_text_color(*COLOR_GRAY)
        subtxt = "Guia completa de todas las funciones disponibles" if self.rol == "admin" else "Guia de uso de todas las funciones disponibles para ti"
        self.cell(0, 8, subtxt, align="C", new_x="LMARGIN", new_y="NEXT")
        self.ln(30)
        # URL
        self.set_font("Helvetica", "", 9)
        self.set_text_color(100, 116, 139)
        self.cell(0, 8, f"URL: {URL_APP}", align="C", new_x="LMARGIN", new_y="NEXT")
        self.ln(4)
        self.set_font("Helvetica", "I", 9)
        self.cell(0, 8, "Documento generado para uso interno", align="C", new_x="LMARGIN", new_y="NEXT")

    # ── Índice ──
    def indice(self, secciones):
        self.add_page()
        self.set_font("Helvetica", "B", 16)
        self.set_text_color(*self.color_accent)
        self.cell(0, 12, "Indice de Funciones", align="L", new_x="LMARGIN", new_y="NEXT")
        self.ln(4)
        self.set_draw_color(*self.color_accent)
        self.set_line_width(0.5)
        self.line(15, self.get_y(), 80, self.get_y())
        self.ln(8)

        for i, sec in enumerate(secciones, 1):
            y_start = self.get_y()
            # Número circular
            self.set_fill_color(*self.color_accent)
            self.set_font("Helvetica", "B", 9)
            self.set_text_color(15, 23, 42)
            self.cell(8, 8, str(i), align="C", fill=True, new_x="RIGHT", new_y="TOP")
            self.set_x(self.get_x() + 3)
            # Título
            self.set_font("Helvetica", "", 11)
            self.set_text_color(60, 60, 60)
            self.cell(0, 8, sec["titulo"], new_x="LMARGIN", new_y="NEXT")
            # Línea separadora
            self.set_draw_color(220, 220, 220)
            self.set_line_width(0.15)
            self.line(15, self.get_y() + 1, self.w - 15, self.get_y() + 1)
            self.ln(4)

    # ── Secciones ──
    def secciones(self, secciones):
        for i, sec in enumerate(secciones, 1):
            # Check si necesitamos nueva página (al menos 50mm libres)
            if self.get_y() > self.h - 60:
                self.add_page()

            # Header de sección
            self.set_fill_color(*self.color_accent)
            self.set_font("Helvetica", "B", 12)
            self.set_text_color(255, 255, 255)
            self.cell(10, 10, str(i), align="C", fill=True, new_x="RIGHT", new_y="TOP")
            self.set_x(self.get_x() + 4)
            self.set_text_color(*self.color_accent)
            self.cell(0, 6, sec["titulo"], new_x="LMARGIN", new_y="NEXT")
            x_after_title = 29
            self.set_x(x_after_title)
            self.set_font("Helvetica", "I", 9)
            self.set_text_color(*COLOR_GRAY)
            self.cell(0, 5, sec["sub"], new_x="LMARGIN", new_y="NEXT")
            self.ln(6)

            # Pasos
            for j, paso in enumerate(sec["pasos"], 1):
                if self.get_y() > self.h - 30:
                    self.add_page()
                self.set_x(20)
                self.set_fill_color(230, 230, 230)
                self.set_font("Helvetica", "B", 8)
                self.set_text_color(80, 80, 80)
                self.cell(7, 7, str(j), align="C", fill=True, new_x="RIGHT", new_y="TOP")
                self.set_x(self.get_x() + 3)
                self.set_font("Helvetica", "", 10)
                self.set_text_color(50, 50, 50)
                # Multi-cell para texto largo
                x_text = self.get_x()
                w_text = self.w - x_text - 15
                self.multi_cell(w_text, 6, paso, new_x="LMARGIN", new_y="NEXT")
                self.ln(2)

            # Nota
            if sec.get("nota"):
                if self.get_y() > self.h - 25:
                    self.add_page()
                tipo = sec.get("nota_tipo", "info")
                if tipo == "aviso":
                    fill_c = (255, 251, 235)
                    borde_c = COLOR_YELLOW
                    txt_c = (146, 120, 20)
                    icono = "(!)"
                elif tipo == "ok":
                    fill_c = (236, 253, 245)
                    borde_c = COLOR_GREEN
                    txt_c = (22, 101, 52)
                    icono = "(v)"
                else:
                    fill_c = (239, 246, 255)
                    borde_c = COLOR_BLUE
                    txt_c = (30, 64, 175)
                    icono = "(i)"

                self.set_x(20)
                y0 = self.get_y()
                self.set_fill_color(*fill_c)
                self.set_font("Helvetica", "", 9)
                self.set_text_color(*txt_c)
                # Caja de nota
                w_nota = self.w - 35
                self.set_x(20)
                self.multi_cell(w_nota, 5.5, f"  {icono} {sec['nota']}", fill=True, new_x="LMARGIN", new_y="NEXT")
                y1 = self.get_y()
                # Borde izquierdo
                self.set_draw_color(*borde_c)
                self.set_line_width(0.8)
                self.line(20, y0, 20, y1)

            self.ln(10)


def generar_pdf(rol, ruta_salida):
    if rol == "admin":
        color = COLOR_GOLD
        secs = SECCIONES_ADMIN
    else:
        color = COLOR_BLUE
        secs = SECCIONES_INVITADO

    pdf = ManualPDF(rol, color)
    pdf.alias_nb_pages()
    pdf.portada()
    pdf.indice(secs)
    pdf.secciones(secs)

    pdf.output(ruta_salida)
    print(f"PDF generado: {ruta_salida}")


if __name__ == "__main__":
    tipo = sys.argv[1] if len(sys.argv) > 1 else "ambos"
    ruta_base = sys.argv[2] if len(sys.argv) > 2 else "."

    os.makedirs(ruta_base, exist_ok=True)

    if tipo in ("admin", "ambos"):
        generar_pdf("admin", os.path.join(ruta_base, "Manual_Administrador_Aduanas_RD.pdf"))
    if tipo in ("invitado", "ambos"):
        generar_pdf("invitado", os.path.join(ruta_base, "Manual_Invitado_Aduanas_RD.pdf"))
    if tipo == "ambos":
        print("Ambos manuales generados exitosamente.")
