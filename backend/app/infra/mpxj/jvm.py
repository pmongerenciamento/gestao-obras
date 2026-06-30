"""Ciclo de vida da JVM usada pelo MPXJ para ler .mpp/.xml/.xer.

A JVM é processo único por instância do app: deve ser iniciada uma vez no
startup (lifespan do FastAPI) e encerrada no shutdown. Uma vez encerrada,
o JPype não permite reiniciá-la no mesmo processo Python.
"""
from __future__ import annotations

import logging

import jpype

import mpxj  # noqa: F401 — importar registra os .jar do MPXJ no classpath antes do startJVM()

logger = logging.getLogger(__name__)


def start_jvm() -> None:
    """Inicia a JVM com o classpath do MPXJ. Idempotente."""
    if jpype.isJVMStarted():
        return
    jpype.startJVM()
    logger.info("JVM iniciada (MPXJ)")


def shutdown_jvm() -> None:
    """Encerra a JVM. Idempotente."""
    if not jpype.isJVMStarted():
        return
    jpype.shutdownJVM()
    logger.info("JVM encerrada (MPXJ)")


def is_jvm_running() -> bool:
    return jpype.isJVMStarted()
