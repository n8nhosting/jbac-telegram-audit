"""In-process schedule (Asia/Yangon): public collector, rollup, alerts, optional MTProto collector.

The tick functions are plain coroutines (tested); build_scheduler only wires them to APScheduler.
"""
from __future__ import annotations

import datetime as dt
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from .alerts import maybe_send
from .collector import run_public_collector
from .rollup import rollup_date
from .rules import now_local

log = logging.getLogger("audit.scheduler")
FINAL_ALERT_TIME = dt.time(0, 6)


async def rollup_tick(conn, settings, now=None, sender=None) -> list[str]:
    """Roll up today and yesterday, re-roll any older day still stuck at 'waiting' (e.g. after downtime),
    and send yesterday's final alert if the 00:06 cron was missed. Returns the dates processed."""
    now = now or now_local(settings.tz)
    today = now.date().isoformat()
    yesterday = (now.date() - dt.timedelta(days=1)).isoformat()
    stuck = [r["local_date"] for r in conn.execute(
        "SELECT DISTINCT local_date FROM daily_rollup WHERE status='waiting' AND local_date < ? ORDER BY local_date DESC", (yesterday,))]
    dates = [today, yesterday] + stuck
    for day in dates:
        rollup_date(conn, day, settings, now)
    if now.time() >= FINAL_ALERT_TIME:
        await maybe_send(conn, settings, yesterday, "final", sender=sender)
    return dates


async def alert_tick(conn, settings, day: str, kind: str, now=None, collector=None, sender=None) -> bool:
    """Collect (optional), roll the day up, then send one alert of `kind` — never twice for the same day."""
    if conn.execute("SELECT 1 FROM alerts WHERE local_date=? AND kind=?", (day, kind)).fetchone():
        return False
    now = now or now_local(settings.tz)
    if collector is not None:
        await collector(conn, settings)
    rollup_date(conn, day, settings, now)
    return await maybe_send(conn, settings, day, kind, sender=sender)


def build_scheduler(settings, conn_factory) -> AsyncIOScheduler:
    tz = settings.tz
    sched = AsyncIOScheduler(timezone=tz)

    async def job_collector():
        conn = conn_factory()
        try:
            st = await run_public_collector(conn, settings, log=log.info)
            log.info("collector done %s", st.as_dict())
        finally:
            conn.close()

    async def job_rollup():
        conn = conn_factory()
        try:
            dates = await rollup_tick(conn, settings)
            log.info("rollup %s", dates)
        finally:
            conn.close()

    async def job_alert(kind: str, day_offset: int = 0, collect_first: bool = False):
        conn = conn_factory()
        try:
            now = now_local(tz)
            day = (now.date() - dt.timedelta(days=day_offset)).isoformat()
            collector = (lambda c, s: run_public_collector(c, s, log=log.info)) if collect_first else None
            sent = await alert_tick(conn, settings, day, kind, now, collector=collector)
            log.info("alert %s %s sent=%s", kind, day, sent)
        finally:
            conn.close()

    async def job_mtproto():
        from .mtproto import run_mtproto_collector
        conn = conn_factory()
        try:
            st = await run_mtproto_collector(conn, settings, log=log.info)
            log.info("mtproto done %s", st)
        finally:
            conn.close()

    start = dt.datetime.now(dt.timezone.utc)
    sched.add_job(job_collector, IntervalTrigger(minutes=settings.collector_interval_min, timezone=tz), id="collector",
                  next_run_time=start + dt.timedelta(seconds=20), max_instances=1, coalesce=True, misfire_grace_time=600)
    sched.add_job(job_rollup, IntervalTrigger(minutes=15, timezone=tz), id="rollup",
                  next_run_time=start + dt.timedelta(seconds=90), max_instances=1, coalesce=True, misfire_grace_time=600)
    sched.add_job(job_alert, CronTrigger(hour=18, minute=0, timezone=tz), args=["warn"], id="alert_warn", misfire_grace_time=1800)
    sched.add_job(job_alert, CronTrigger(hour=23, minute=50, timezone=tz), args=["summary"], id="alert_summary", misfire_grace_time=600)
    # final verdict for yesterday: fresh collection first so a 23:40 post is not missed
    sched.add_job(job_alert, CronTrigger(hour=0, minute=6, timezone=tz), args=["final", 1, True], id="alert_final", misfire_grace_time=3600)
    if settings.mtproto_enabled:
        sched.add_job(job_mtproto, IntervalTrigger(minutes=30, timezone=tz), id="mtproto",
                      next_run_time=start + dt.timedelta(minutes=5), max_instances=1, coalesce=True, misfire_grace_time=600)
    return sched
