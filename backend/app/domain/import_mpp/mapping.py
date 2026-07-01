"""Mapeia org.mpxj.ProjectFile (lido via infra/mpxj) para as tuplas aceitas
pelos bulk inserts de infra/db/bulk.py.

Este módulo só extrai o que está no arquivo — não decide nada sobre
snapshots/baseline (isso é domain/snapshots). planned_start/planned_finish
vêm do Baseline Start/Finish do MS Project: os engenheiros deste time salvam
baseline no .mpp antes de importar, então esses campos chegam preenchidos na
prática. Sem fallback para Start/Finish atual por decisão — se um arquivo
sem baseline salvo aparecer, é melhor planned_* vir None (visível) do que
silenciosamente virar igual ao forecast.
"""
from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID

# Task uid 0 é a "project summary task" sintética que o MPXJ expõe quando o
# .mpp tem essa opção habilitada — espelha o projeto inteiro (mesmo nome,
# mesmas datas de início/fim do projeto), não é uma tarefa real do WBS.
_PROJECT_SUMMARY_UID = 0


def _real_tasks(project: Any) -> list[Any]:
    return [
        t for t in project.getTasks()
        if t is not None and int(t.getUniqueID()) != _PROJECT_SUMMARY_UID
    ]


def _to_date(value: Any) -> date | None:
    """java.time.LocalDateTime -> date (task_progress guarda só a data, sem hora)."""
    if value is None:
        return None
    return date(value.getYear(), value.getMonthValue(), value.getDayOfMonth())


def _duration_days(duration: Any, properties: Any) -> float | None:
    """org.mpxj.Duration em qualquer unidade -> dias (tasks.duration é numeric)."""
    if duration is None:
        return None
    from org.mpxj import TimeUnit

    normalized = duration.convertUnits(TimeUnit.DAYS, properties)
    return round(float(normalized.getDuration()), 2)


def _lag_days(duration: Any, properties: Any) -> int:
    """org.mpxj.Duration do lag -> inteiro de dias (dependencies.lag_days)."""
    if duration is None:
        return 0
    from org.mpxj import TimeUnit

    normalized = duration.convertUnits(TimeUnit.DAYS, properties)
    return round(float(normalized.getDuration()))


def _task_type(task: Any) -> str:
    """'summary' | 'milestone' | 'task' — usado para filtrar linhas de WBS
    (summary) das visões operacionais (Linha de Balanço, Gestão à Vista).
    Não é o TaskType do MPXJ (FIXED_DURATION/FIXED_UNITS/FIXED_WORK), que é
    detalhe de cálculo de agenda do MS Project e não interessa a este sistema.
    """
    if task.getSummary():
        return "summary"
    if task.getMilestone():
        return "milestone"
    return "task"


def map_tasks(project: Any, project_id: UUID) -> list[tuple]:
    """ProjectFile -> tuplas na ordem de infra.db.bulk.TASK_COLUMNS:
    (project_id, ms_uid, wbs, name, level, type, duration, is_milestone)
    """
    properties = project.getProjectProperties()
    rows = []
    for task in _real_tasks(project):
        wbs = task.getWBS()
        name = task.getName()
        level = task.getOutlineLevel()
        rows.append((
            project_id,
            int(task.getUniqueID()),
            str(wbs) if wbs is not None else None,
            str(name) if name is not None else "",
            int(level) if level is not None else None,
            _task_type(task),
            _duration_days(task.getDuration(), properties),
            bool(task.getMilestone()),
        ))
    return rows


def map_dependencies(project: Any, project_id: UUID) -> list[tuple]:
    """ProjectFile -> tuplas na ordem de infra.db.bulk.DEPENDENCY_COLUMNS:
    (project_id, predecessor_uid, successor_uid, type, lag_days)
    """
    properties = project.getProjectProperties()
    rows = []
    for task in _real_tasks(project):
        predecessors = task.getPredecessors()
        if not predecessors:
            continue
        for relation in predecessors:
            predecessor_task = relation.getPredecessorTask()
            if predecessor_task is None:
                continue  # vínculo externo (outro arquivo/projeto) — sem uid local
            rows.append((
                project_id,
                int(predecessor_task.getUniqueID()),
                int(task.getUniqueID()),
                str(relation.getType()),
                _lag_days(relation.getLag(), properties),
            ))
    return rows


def map_task_progress(
    project: Any, snapshot_id: UUID, task_id_map: dict[int, UUID]
) -> list[tuple]:
    """ProjectFile -> tuplas na ordem de infra.db.bulk.TASK_PROGRESS_COLUMNS:
    (snapshot_id, task_id, planned_start, planned_finish, forecast_start,
    forecast_finish, actual_start, actual_finish, percent_complete)

    task_id_map vem de fetch_task_id_map() (ms_uid -> id), chamado depois de
    bulk_insert_tasks — COPY não faz RETURNING, então os ids têm que ser
    buscados antes de montar essas tuplas.

    planned_start/planned_finish vêm do Baseline Start/Finish do MS Project
    (sem fallback — ver docstring do módulo).
    """
    rows = []
    for task in _real_tasks(project):
        ms_uid = int(task.getUniqueID())
        task_id = task_id_map.get(ms_uid)
        if task_id is None:
            continue  # tarefa não inserida (ex: filtrada em map_tasks)

        percent = task.getPercentageComplete()
        rows.append((
            snapshot_id,
            task_id,
            _to_date(task.getBaselineStart()),
            _to_date(task.getBaselineFinish()),
            _to_date(task.getStart()),
            _to_date(task.getFinish()),
            _to_date(task.getActualStart()),
            _to_date(task.getActualFinish()),
            float(percent) if percent is not None else None,
        ))
    return rows
