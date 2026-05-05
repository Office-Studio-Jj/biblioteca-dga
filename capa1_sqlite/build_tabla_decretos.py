"""
build_tabla_decretos.py — Crea tabla_decretos en arancel_rd.db
Orden CEO 05-05-2026: Schema para decretos que modifican clasificación arancelaria.
Regla de prelación integrada como constraint lógico.
PROHIBIDO: insertar datos sin validación humana.
"""
import os
import sqlite3

_HERE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(_HERE, "arancel_rd.db")


SQL_CREATE = """
CREATE TABLE IF NOT EXISTS tabla_decretos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    instrumento TEXT NOT NULL,          -- Ej: "Decreto 36-22", "Ley 226-06"
    tipo TEXT NOT NULL CHECK(tipo IN ('ley','decreto','resolucion','convenio')),
    numero TEXT NOT NULL,               -- Ej: "36-22"
    fecha_emision TEXT,                 -- ISO 8601
    fecha_vigencia TEXT,                -- desde cuándo aplica
    contenido_relevante TEXT NOT NULL,  -- qué regula respecto a clasificación
    capitulos_afectados TEXT,           -- JSON array de capítulos SA afectados, ej: [27,87]
    partidas_afectadas TEXT,            -- JSON array de partidas afectadas
    modifica_dai INTEGER DEFAULT 0,     -- 1 si modifica DAI
    modifica_itbis INTEGER DEFAULT 0,
    modifica_isc INTEGER DEFAULT 0,
    exencion_total INTEGER DEFAULT 0,   -- 1 si exime completamente
    regimen_aplicable TEXT,             -- importación definitiva, zona franca, etc.
    estado TEXT NOT NULL DEFAULT 'vigente' CHECK(estado IN ('vigente','derogado','modificado','suspendido')),
    derogado_por TEXT,                  -- referencia al decreto que lo deroga
    fecha_derogacion TEXT,
    prelacion INTEGER DEFAULT 0,        -- mayor = más específico/posterior (prevalece)
    fecha_ultima_auditoria TEXT,        -- última vez que se verificó vigencia
    auditor TEXT,                       -- quién lo verificó
    notas TEXT,                         -- observaciones libres
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_decretos_estado ON tabla_decretos(estado);
CREATE INDEX IF NOT EXISTS idx_decretos_tipo ON tabla_decretos(tipo);
CREATE INDEX IF NOT EXISTS idx_decretos_capitulos ON tabla_decretos(capitulos_afectados);

-- Tabla de log de cambios (CEO 2.5: log obligatorio)
CREATE TABLE IF NOT EXISTS decretos_changelog (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    decreto_id INTEGER NOT NULL,
    accion TEXT NOT NULL CHECK(accion IN ('crear','modificar','derogar','auditar')),
    campo_modificado TEXT,
    valor_anterior TEXT,
    valor_nuevo TEXT,
    fundamento_legal TEXT NOT NULL,     -- por qué se hizo el cambio
    autor TEXT NOT NULL,
    fecha TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (decreto_id) REFERENCES tabla_decretos(id)
);
"""

SQL_PRELACION = """
-- Vista: regla de prelación CEO (Sección 2.7)
-- 1. Ley especial > ley general (prelación mayor)
-- 2. Norma posterior > norma anterior (fecha_vigencia)
-- 3. Conflicto irreconciliable → detener clasificación
CREATE VIEW IF NOT EXISTS v_decretos_por_prelacion AS
SELECT *,
    CASE
        WHEN estado != 'vigente' THEN -999
        ELSE prelacion * 1000 + CAST(REPLACE(REPLACE(fecha_vigencia,'-',''),'T','') AS INTEGER)
    END AS score_prelacion
FROM tabla_decretos
WHERE estado = 'vigente'
ORDER BY score_prelacion DESC;
"""


def build():
    if not os.path.exists(DB_PATH):
        print(f"ERROR: {DB_PATH} no existe.")
        return False
    con = sqlite3.connect(DB_PATH)
    con.executescript(SQL_CREATE)
    con.executescript(SQL_PRELACION)
    con.commit()
    print("[OK] tabla_decretos creada con schema CEO 05-05-2026")
    print("[OK] decretos_changelog creada (log obligatorio)")
    print("[OK] v_decretos_por_prelacion creada (regla prelación)")
    print("[AVISO] Tabla VACÍA. Insertar datos requiere validación humana. Cero tolerancia.")
    con.close()
    return True


if __name__ == "__main__":
    build()
