from __future__ import annotations

import itertools
import logging
import queue
import threading
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import SessionLocal
from .errors import AppError
from .models import Job, Node, User
from .notifications import notify_job_failure
from .timeutil import to_iso, utcnow

logger = logging.getLogger("oxidized_ui.jobs")

JobRunner = Callable[[Session, Job], dict[str, Any] | None]
_executor: ThreadPoolExecutor | None = None
_futures: dict[int, Future] = {}
_cancelled: set[int] = set()
_priority_queue: queue.PriorityQueue | None = None
_dispatcher: threading.Thread | None = None
_sequence = itertools.count()
_sentinel = (-1, 0, 0, None)
_stopping = threading.Event()


def _get_executor() -> ThreadPoolExecutor:
    global _executor
    if _executor is None:
        _executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="oxidized-job")
    return _executor


def _get_queue() -> queue.PriorityQueue:
    global _priority_queue, _dispatcher
    if _priority_queue is None:
        _priority_queue = queue.PriorityQueue()
    if _dispatcher is None or not _dispatcher.is_alive():
        _stopping.clear()
        _dispatcher = threading.Thread(target=_dispatch, name="oxidized-job-queue", daemon=True)
        _dispatcher.start()
    return _priority_queue


def _dispatch() -> None:
    assert _priority_queue is not None
    while not _stopping.is_set():
        item = _priority_queue.get()
        if item is _sentinel or item[3] is None:
            _priority_queue.task_done()
            break
        priority, _, job_id, runner = item
        try:
            if job_id in _cancelled:
                continue
            with SessionLocal() as db:
                job = db.get(Job, job_id)
                if job is None or job.status == "cancelled":
                    continue
            _futures[job_id] = _get_executor().submit(_execute, job_id, runner)
        finally:
            _priority_queue.task_done()


def shutdown_jobs() -> None:
    global _executor, _priority_queue, _dispatcher
    _stopping.set()
    if _priority_queue is not None:
        _priority_queue.put(_sentinel)
    if _dispatcher is not None:
        _dispatcher.join(timeout=2)
        _dispatcher = None
    if _executor is not None:
        _executor.shutdown(wait=False, cancel_futures=True)
        _executor = None
    _priority_queue = None


def create_job(
    db: Session,
    *,
    kind: str,
    actor_id: int | None,
    payload: dict[str, Any] | None = None,
    node_id: int | None = None,
    progress_total: int = 0,
    priority: int = 5,
) -> Job:
    job = Job(
        kind=kind,
        status="queued",
        node_id=node_id,
        created_by_id=actor_id,
        progress_total=progress_total,
        progress_done=0,
        payload=payload or {},
        priority=max(1, min(10, priority)),
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def create_and_submit(
    db: Session,
    *,
    kind: str,
    actor_id: int,
    runner: JobRunner,
    payload: dict[str, Any] | None = None,
    node_id: int | None = None,
    progress_total: int = 0,
) -> Job:
    from .priority_service import priority_for

    priority = priority_for(db, node_id=node_id, payload=payload)
    job = create_job(
        db,
        kind=kind,
        actor_id=actor_id,
        payload=payload,
        node_id=node_id,
        progress_total=progress_total,
        priority=priority,
    )
    submit(job.id, runner, priority=priority)
    return job


def submit(job_id: int, runner: JobRunner, *, priority: int = 5) -> None:
    _get_queue().put((max(1, min(10, priority)), next(_sequence), job_id, runner))


def cancel_job(db: Session, job_id: int) -> Job:
    job = db.get(Job, job_id)
    if job is None:
        raise AppError("job.not_found")
    if job.status in {"succeeded", "failed", "cancelled"}:
        raise AppError("job.not_cancellable", params={"status": job.status})
    _cancelled.add(job_id)
    future = _futures.get(job_id)
    if future is not None:
        future.cancel()
    job.status = "cancelled"
    job.error_code = "job.cancelled"
    job.error_params = {}
    job.finished_at = utcnow()
    db.commit()
    return job


def _execute(job_id: int, runner: JobRunner) -> None:
    with SessionLocal() as db:
        job = db.get(Job, job_id)
        if job is None:
            return
        if job_id in _cancelled:
            return
        job.status = "running"
        job.started_at = utcnow()
        db.commit()
        try:
            result = runner(db, job)
            db.refresh(job)
            if job_id in _cancelled:
                return
            job.result = result or {}
            if isinstance(result, dict) and result.get("ok") is False:
                job.status = "failed"
                job.error_code = str(result.get("error_code") or "app.internal_error")
                job.error_params = {
                    key: value for key, value in result.items() if key in {"queued", "requested", "failed"}
                }
            else:
                job.status = "succeeded"
            job.finished_at = utcnow()
            job.progress_done = job.progress_total or job.progress_done
            db.commit()
        except AppError as exc:
            db.rollback()
            if job_id in _cancelled:
                return
            job = db.get(Job, job_id)
            if job is not None:
                job.status = "failed"
                job.error_code = exc.code
                job.error_params = exc.params
                job.result = exc.fields or None
                job.finished_at = utcnow()
                db.commit()
                notify_job_failure(db, job)
            logger.warning("Job %s failed: %s", job_id, exc.code)
        except Exception:  # noqa: BLE001 - job boundary must never leak
            db.rollback()
            if job_id in _cancelled:
                return
            job = db.get(Job, job_id)
            if job is not None:
                job.status = "failed"
                job.error_code = "app.internal_error"
                job.error_params = {}
                job.finished_at = utcnow()
                db.commit()
                notify_job_failure(db, job)
            logger.exception("Job %s crashed", job_id)
        finally:
            _futures.pop(job_id, None)
            _cancelled.discard(job_id)


def _runner_for_kind(kind: str):
    from .backup_service import run_backup_all_job, run_backup_node_job
    from .config_service import run_config_apply_job
    from .export_service import run_export_job
    from .facts_service import run_facts_job
    from .report_service import run_report_job

    if kind == "backup_node":
        return run_backup_node_job
    if kind == "backup_all":
        return run_backup_all_job
    if kind == "backup_export":
        return run_export_job
    if kind == "facts_collect":
        return run_facts_job
    if kind == "report":
        return run_report_job
    if kind == "config_apply":
        return run_config_apply_job
    if kind == "oxidized_restart":
        from .routers.status import _restart_runner

        return _restart_runner
    return None


def interrupt_incomplete_jobs(db: Session) -> int:
    """Fail running jobs, but keep queued work durable across a restart."""
    jobs = db.scalars(select(Job).where(Job.status.in_(("queued", "running")))).all()
    now = utcnow()
    queued = 0
    for job in jobs:
        if job.status == "queued":
            runner = _runner_for_kind(job.kind)
            if runner is not None:
                submit(job.id, runner, priority=job.priority)
                queued += 1
                continue
        job.status = "failed"
        job.error_code = "job.interrupted"
        job.error_params = {}
        job.finished_at = now
    if jobs:
        db.commit()
    return queued


def update_progress(db: Session, job: Job, *, done: int, total: int | None = None) -> None:
    job.progress_done = done
    if total is not None:
        job.progress_total = total
    db.commit()


def serialize_job(db: Session, job: Job) -> dict[str, Any]:
    actor = db.get(User, job.created_by_id) if job.created_by_id else None
    node = db.get(Node, job.node_id) if job.node_id else None
    error = None
    if job.error_code:
        error = {"code": job.error_code, "params": job.error_params or {}}
    return {
        "id": job.id,
        "kind": job.kind,
        "status": job.status,
        "progress": {"done": job.progress_done, "total": job.progress_total},
        "priority": job.priority,
        "node_id": job.node_id,
        "node_name": node.name if node is not None else (job.payload or {}).get("name"),
        "created_by": ({"id": actor.id, "username": actor.username} if actor is not None else None),
        "created_at": to_iso(job.created_at),
        "started_at": to_iso(job.started_at),
        "finished_at": to_iso(job.finished_at),
        "error": error,
        "result": job.result,
    }
