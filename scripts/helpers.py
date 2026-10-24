from datetime import datetime
import logging
import os
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

FILAS_ESPERADAS = 1030
PLANTAS_ESPERADAS = 12

COLUMNAS_ESPERADAS = [
    "id_ensayo",
    "planta_id",
    "planta_nombre",
    "ciudad",
    "departamento",
    "cemento_kg_m3",
    "escoria_alto_horno_kg_m3",
    "ceniza_volante_kg_m3",
    "agua_kg_m3",
    "superplastificante_kg_m3",
    "agregado_grueso_kg_m3",
    "agregado_fino_kg_m3",
    "edad_dias",
    "resistencia_compresion_mpa",
]

def add_date_suffix(filename, date=None):
    """
    Appends _YYYYMMDD to the filename before the extension.
    
    Args:
        filename (str): Original filename (e.g. 'data.csv')
        date (datetime, optional): Date to use; defaults to today.
    
    Returns:
        str: Modified filename (e.g. 'data_20250501.csv')
    """
    if date is None:
        date = datetime.today()
        
    name, ext = os.path.splitext(filename)
    date_str = date.strftime("%Y%m%d")
    return f"{name}_{date_str}{ext}"

def leer_datos(path):
    return pd.read_csv(path)

def transformar_datos(df):
    df['total'] = df['cantidad'] * df['precio']
    return df

def resumir_datos(df):
    resumen = df.groupby('producto')['total'].sum().reset_index()
    return resumen

def guardar_datos(df, path):
    df.to_csv(path, index=False)


def listar_csv_plantas(directorio: str | Path) -> list[str]:
    """Recorre el servidor central y sus subcarpetas y devuelve los CSV.

    El orden es alfabético para que dos ejecuciones con los mismos archivos
    produzcan el mismo consolidado.
    """
    raiz = Path(directorio)
    if not raiz.is_dir():
        raise FileNotFoundError(
            f"No existe el servidor central: {raiz}. "
            "Cada planta debe dejar su CSV en una subcarpeta."
        )

    archivos = sorted(
        ruta
        for ruta in raiz.rglob("*.csv")
        if ruta.is_file() and not ruta.name.startswith("_")
    )
    if not archivos:
        raise FileNotFoundError(
            f"No hay CSV dentro de las subcarpetas de {raiz}."
        )

    logger.info("Se encontraron %s CSV en %s", len(archivos), raiz)
    return [str(ruta) for ruta in archivos]


def consolidar_plantas(rutas: list[str], archivo_salida: str | Path) -> dict:
    """Lee los CSV de las plantas y escribe un único archivo consolidado.

    Agrega ``archivo_origen`` para saber de qué subcarpeta salió cada fila.
    No imputa nulos ni borra duplicados del laboratorio: si el mismo
    ``id_ensayo`` aparece dos veces al unir, la tarea falla.
    """
    if not rutas:
        raise ValueError("La lista de archivos de planta está vacía.")

    marcos = []
    columnas_referencia = None

    for ruta in rutas:
        marco = pd.read_csv(ruta)
        if marco.empty:
            raise ValueError(f"El archivo de planta está vacío: {ruta}")

        columnas = list(marco.columns)
        faltantes = [columna for columna in COLUMNAS_ESPERADAS if columna not in columnas]
        if faltantes:
            raise ValueError(f"{ruta} no trae las columnas {faltantes}.")
        if columnas_referencia is None:
            columnas_referencia = columnas
        elif columnas != columnas_referencia:
            raise ValueError(
                f"Esquema distinto en {ruta}. "
                f"Esperado {columnas_referencia}, llegó {columnas}."
            )

        origen = Path(ruta)
        marco = marco.copy()
        marco["archivo_origen"] = f"{origen.parent.name}/{origen.name}"
        marcos.append(marco)

    consolidado = pd.concat(marcos, ignore_index=True)
    repetidos = consolidado.loc[consolidado["id_ensayo"].duplicated(), "id_ensayo"]
    if not repetidos.empty:
        muestra = repetidos.astype(int).tolist()[:10]
        raise ValueError(f"id_ensayo repetido al consolidar: {muestra}")

    plantas = sorted(consolidado["planta_id"].dropna().astype(str).unique().tolist())
    if len(plantas) != PLANTAS_ESPERADAS:
        raise ValueError(
            f"Se esperaban {PLANTAS_ESPERADAS} plantas y llegaron {len(plantas)}: {plantas}"
        )
    if len(consolidado) != FILAS_ESPERADAS:
        raise ValueError(
            f"Se esperaban {FILAS_ESPERADAS} filas y el consolidado tiene {len(consolidado)}."
        )

    consolidado = consolidado.sort_values(["planta_id", "id_ensayo"]).reset_index(drop=True)
    salida = Path(archivo_salida)
    salida.parent.mkdir(parents=True, exist_ok=True)
    consolidado.to_csv(salida, index=False)

    resumen = {
        "archivo": str(salida),
        "filas": int(len(consolidado)),
        "plantas": plantas,
        "archivos_leidos": len(rutas),
    }
    logger.info(
        "Consolidado escrito en %s (%s filas, %s plantas)",
        salida,
        resumen["filas"],
        len(plantas),
    )
    return resumen


def validar_consolidado(resumen: dict) -> dict:
    """Vuelve a leer el archivo escrito y confirma filas y plantas."""
    archivo = Path(resumen["archivo"])
    if not archivo.is_file():
        raise FileNotFoundError(f"No se escribió el consolidado: {archivo}")

    verificacion = pd.read_csv(archivo)
    if len(verificacion) != int(resumen["filas"]):
        raise ValueError(
            "El archivo consolidado no coincide con el conteo de la tarea anterior. "
            f"Disco={len(verificacion)} resumen={resumen['filas']}"
        )
    plantas_en_archivo = verificacion["planta_id"].nunique()
    if plantas_en_archivo != PLANTAS_ESPERADAS:
        raise ValueError(
            f"El archivo consolidado tiene {plantas_en_archivo} plantas, "
            f"no {PLANTAS_ESPERADAS}."
        )
    if len(verificacion) != FILAS_ESPERADAS:
        raise ValueError(
            f"El archivo consolidado tiene {len(verificacion)} filas, no {FILAS_ESPERADAS}."
        )

    logger.info("Consolidado válido: %s", archivo)
    return resumen
