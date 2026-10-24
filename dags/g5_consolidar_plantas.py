"""Carga batch del servidor central de Concretera del Pacífico.

Recorre ``/opt/airflow/data/servidor_central`` y sus subcarpetas (un CSV por
planta) y deja un único archivo en ``data/consolidado``. Sustituye la
consolidación manual. La frecuencia es diaria: las plantas pueden dejar el
archivo durante el día y el lote se cierra a las 07:00, hora de Lima.
"""

from datetime import datetime, timedelta
import logging

from airflow.decorators import dag, task
from pendulum import timezone

from scripts.helpers import (
    consolidar_plantas,
    listar_csv_plantas,
    validar_consolidado,
)

SERVIDOR_CENTRAL = "/opt/airflow/data/servidor_central"
ARCHIVO_CONSOLIDADO = "/opt/airflow/data/consolidado/ensayos_resistencia_consolidado.csv"

logger = logging.getLogger("airflow.task")

default_args = {
    "owner": "airflow",
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}


@dag(
    dag_id="g5_consolidar_plantas",
    description="Lee los CSV de las 12 plantas y genera un único archivo consolidado.",
    default_args=default_args,
    start_date=datetime(2025, 1, 1, tzinfo=timezone("America/Lima")),
    schedule="0 7 * * *",
    catchup=False,
    tags=["concretera", "batch", "consolidacion"],
)
def consolidar_ensayos_plantas():

    @task
    def listar_plantas() -> list[str]:
        rutas = listar_csv_plantas(SERVIDOR_CENTRAL)
        logger.info("Plantas a consolidar: %s", rutas)
        return rutas

    @task
    def consolidar(rutas: list[str]) -> dict:
        resumen = consolidar_plantas(rutas, ARCHIVO_CONSOLIDADO)
        logger.info("Archivo único generado: %s", resumen)
        return resumen

    @task
    def validar(resumen: dict) -> dict:
        resultado = validar_consolidado(resumen)
        logger.info(
            "Validación ok: %s filas de %s plantas en %s",
            resultado["filas"],
            len(resultado["plantas"]),
            resultado["archivo"],
        )
        return resultado

    validar(consolidar(listar_plantas()))


dag = consolidar_ensayos_plantas()
