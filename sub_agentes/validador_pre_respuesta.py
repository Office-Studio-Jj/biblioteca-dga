"""
Validador pre-respuesta para clasificaciones arancelarias RD.

Verifica TODOS los campos del informe contra fuentes autoritativas (SQLite Capa 1)
ANTES de enviar la respuesta al usuario. Ningun dato inferido se presenta como oficial.

Base legal: Ley 168-21 Art. 75, Decreto 755-22 Art. 63.
"""

import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from capa1_sqlite.orquestador_capa3 import consultar_son_exacto

# --- Permisos por capitulo (opcional) ---

_PERMISOS_PATH = os.path.join(
    os.path.dirname(__file__), '..', 'notebooklm_skill', 'data', 'permisos_por_capitulo.json'
)
_permisos_cache: dict | None = None


def _cargar_permisos() -> dict | None:
    """Carga permisos_por_capitulo.json si existe. Cache en memoria."""
    global _permisos_cache
    if _permisos_cache is not None:
        return _permisos_cache
    if os.path.isfile(_PERMISOS_PATH):
        with open(_PERMISOS_PATH, encoding='utf-8') as f:
            _permisos_cache = json.load(f)
        return _permisos_cache
    return None


# --- Validadores internos ---

_SON_RE = re.compile(r'^\d{4}\.\d{2}\.\d{2}(\.\d{2})?$')
_RGI_VALIDAS = {1, 2, 3, 4, 5, 6}


def _verificar_son(son: str) -> dict:
    """Verifica que el SON exista en SQLite y devuelve datos oficiales."""
    resultado = {
        'verificado': False,
        'fuente': 'SQLite arancel_rd.db',
        'valor_oficial': None,
        'datos_oficiales': None,
    }
    if not son or not _SON_RE.match(son):
        resultado['error'] = f'Formato SON invalido: {son}'
        return resultado

    datos = consultar_son_exacto(son)
    if datos is None:
        resultado['error'] = f'SON {son} no existe en base de datos'
        return resultado

    resultado['verificado'] = True
    resultado['valor_oficial'] = son
    resultado['datos_oficiales'] = datos
    return resultado


def _verificar_descripcion(desc_informe: str, desc_oficial: str) -> dict:
    """Comparacion fuzzy: primeros 50 caracteres normalizados."""
    resultado = {
        'verificado': False,
        'fuente': 'SQLite arancel_rd.db',
        'valor_oficial': desc_oficial,
    }
    if not desc_informe or not desc_oficial:
        resultado['error'] = 'Descripcion faltante'
        return resultado

    norm_informe = desc_informe.strip().lower()[:50]
    norm_oficial = desc_oficial.strip().lower()[:50]
    if norm_informe == norm_oficial:
        resultado['verificado'] = True
    else:
        resultado['error'] = 'Descripcion no coincide con registro oficial'
    return resultado


def _verificar_tributos(informe: dict, datos_oficiales: dict) -> dict:
    """Verifica DAI, ITBIS e ISC contra SQLite."""
    campos = {}

    # DAI / gravamen
    dai_informe = informe.get('dai_pct') or informe.get('gravamen')
    dai_oficial = datos_oficiales.get('gravamen')
    if dai_oficial is not None and dai_informe is not None:
        match = str(dai_informe).strip() == str(dai_oficial).strip()
        campos['dai_pct'] = {
            'verificado': match,
            'fuente': 'SQLite arancel_rd.db',
            'valor_oficial': dai_oficial,
        }
        if not match:
            campos['dai_pct']['error'] = (
                f'DAI informe={dai_informe}, oficial={dai_oficial}'
            )
    else:
        campos['dai_pct'] = {
            'verificado': False,
            'fuente': 'NO VERIFICADO — Requiere validacion manual',
            'valor_oficial': dai_oficial,
        }

    # ITBIS
    itbis_informe = informe.get('itbis_pct')
    itbis_oficial = datos_oficiales.get('itbis')
    if itbis_oficial is not None and itbis_informe is not None:
        match = str(itbis_informe).strip() == str(itbis_oficial).strip()
        campos['itbis_pct'] = {
            'verificado': match,
            'fuente': 'SQLite arancel_rd.db (Ley 11-92)',
            'valor_oficial': itbis_oficial,
        }
        if not match:
            campos['itbis_pct']['error'] = (
                f'ITBIS informe={itbis_informe}, oficial={itbis_oficial}'
            )
    else:
        campos['itbis_pct'] = {
            'verificado': False,
            'fuente': 'NO VERIFICADO — Requiere validacion manual',
            'valor_oficial': itbis_oficial,
        }

    # ISC
    isc_informe = informe.get('isc')
    isc_oficial = datos_oficiales.get('isc')
    if isc_oficial is not None and isc_informe is not None:
        match = str(isc_informe).strip() == str(isc_oficial).strip()
        campos['isc'] = {
            'verificado': match,
            'fuente': 'SQLite arancel_rd.db (Ley 11-92)',
            'valor_oficial': isc_oficial,
        }
        if not match:
            campos['isc']['error'] = (
                f'ISC informe={isc_informe}, oficial={isc_oficial}'
            )
    else:
        campos['isc'] = {
            'verificado': False,
            'fuente': 'NO VERIFICADO — Requiere validacion manual',
            'valor_oficial': isc_oficial,
        }

    return campos


# --- Validador principal ---

def validar_respuesta(informe: dict) -> dict:
    """
    Valida un informe de clasificacion contra fuentes autoritativas.

    Parametros:
        informe: dict con claves son, descripcion, dai_pct, itbis_pct, isc,
                 permisos, rgi_aplicada.

    Retorna:
        {
            valido: bool,
            campos_verificados: {campo: {verificado, fuente, valor_oficial}},
            advertencias: [str],
            informe_corregido: dict
        }

    Base legal: Ley 168-21 Art. 75, Decreto 755-22 Art. 63.
    """
    campos_verificados = {}
    advertencias = []
    corregido = dict(informe)

    # 1. Verificar SON
    son = informe.get('son', '')
    ver_son = _verificar_son(son)
    campos_verificados['son'] = {
        'verificado': ver_son['verificado'],
        'fuente': ver_son['fuente'],
        'valor_oficial': ver_son.get('valor_oficial'),
    }
    if not ver_son['verificado']:
        advertencias.append(
            ver_son.get('error', f'SON {son} no pudo ser verificado')
        )

    datos_oficiales = ver_son.get('datos_oficiales') or {}

    # 2. Verificar descripcion
    if datos_oficiales:
        ver_desc = _verificar_descripcion(
            informe.get('descripcion', ''),
            datos_oficiales.get('descripcion', ''),
        )
        campos_verificados['descripcion'] = {
            'verificado': ver_desc['verificado'],
            'fuente': ver_desc['fuente'],
            'valor_oficial': ver_desc['valor_oficial'],
        }
        if not ver_desc['verificado']:
            advertencias.append(
                ver_desc.get('error', 'Descripcion no verificada')
            )
            corregido['descripcion'] = datos_oficiales.get('descripcion')
    else:
        campos_verificados['descripcion'] = {
            'verificado': False,
            'fuente': 'NO VERIFICADO — Requiere validacion manual',
            'valor_oficial': None,
        }

    # 3. Verificar tributos (DAI, ITBIS, ISC)
    if datos_oficiales:
        tributos = _verificar_tributos(informe, datos_oficiales)
        campos_verificados.update(tributos)
        for campo, detalle in tributos.items():
            if not detalle['verificado'] and detalle.get('valor_oficial') is not None:
                advertencias.append(
                    detalle.get('error', f'{campo}: discrepancia con SQLite')
                )
                # Corregir con valor oficial
                corregido[campo] = detalle['valor_oficial']
    else:
        for campo in ('dai_pct', 'itbis_pct', 'isc'):
            campos_verificados[campo] = {
                'verificado': False,
                'fuente': 'NO VERIFICADO — Requiere validacion manual',
                'valor_oficial': None,
            }

    # 4. Verificar permisos contra permisos_por_capitulo.json
    permisos_informe = informe.get('permisos')
    permisos_db = _cargar_permisos()
    if permisos_informe and permisos_db and son:
        capitulo = son[:2]
        permisos_oficiales = permisos_db.get(capitulo)
        if permisos_oficiales is not None:
            campos_verificados['permisos'] = {
                'verificado': True,
                'fuente': 'permisos_por_capitulo.json',
                'valor_oficial': permisos_oficiales,
            }
        else:
            campos_verificados['permisos'] = {
                'verificado': False,
                'fuente': 'NO VERIFICADO — Capitulo sin datos de permisos',
                'valor_oficial': None,
            }
    else:
        campos_verificados['permisos'] = {
            'verificado': False,
            'fuente': 'NO VERIFICADO — Requiere validacion manual',
            'valor_oficial': None,
        }

    # 5. Verificar RGI aplicada (1-6)
    rgi = informe.get('rgi_aplicada')
    if rgi is not None:
        try:
            rgi_num = int(rgi)
        except (ValueError, TypeError):
            rgi_num = None
        if rgi_num in _RGI_VALIDAS:
            campos_verificados['rgi_aplicada'] = {
                'verificado': True,
                'fuente': 'Decreto 755-22 RGI 1-6',
                'valor_oficial': rgi_num,
            }
        else:
            campos_verificados['rgi_aplicada'] = {
                'verificado': False,
                'fuente': 'Decreto 755-22',
                'valor_oficial': None,
            }
            advertencias.append(f'RGI invalida: {rgi}. Debe ser 1-6.')
    else:
        campos_verificados['rgi_aplicada'] = {
            'verificado': False,
            'fuente': 'NO VERIFICADO — Requiere validacion manual',
            'valor_oficial': None,
        }
        advertencias.append('RGI no especificada en el informe.')

    # Resultado final
    valido = all(
        v.get('verificado', False) for v in campos_verificados.values()
    )

    return {
        'valido': valido,
        'campos_verificados': campos_verificados,
        'advertencias': advertencias,
        'informe_corregido': corregido,
    }
