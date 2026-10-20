"""Automatic, restart-safe scheduler for reservation reminder emails.

The scheduler starts with the Django backend (``ReservationsConfig.ready``),
runs an immediate catch-up sweep, then checks once an hour. It is deliberately
disabled for management commands, migrations, and tests.

Multiple backend workers may each start a scheduler thread. A short-lived
database lease (``ReminderSchedulerLease``) elects exactly ONE active leader:
the others keep waiting and take over automatically if the leader dies. Even if
two checks ever overlapped, the per-reservation email claim in
``reservations.services.reminders`` guarantees each reminder is emailed once.

Production options:

* Default: leave the in-process scheduler enabled. The lease makes it safe with
  gunicorn/uWSGI workers or multiple container instances.
* Dedicated worker: set ``REMINDER_SCHEDULER_ENABLED=false`` on web processes
  and run ``python manage.py run_reminder_scheduler`` as a separate service.
  Both options use the same lease and the same idempotent sweep.
"""

from __future__ import annotations

import atexit
import logging
import os
import sys
import threading
import time
import uuid
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from reservations.models import ReminderSchedulerLease

logger = logging.getLogger(__name__)

LEASE_NAME = "reservation-reminder-scheduler"

_started = False
_start_lock = threading.Lock()
_stop_event = threading.Event()


def _management_command(argv: list[str]) -> str | None:
    """Return the subcommand when ``argv`` is a Django management command."""
    if not argv:
        return None
    executable = os.path.basename(argv[0]).lower()
    if executable not in {"manage.py", "django-admin", "django-admin.py"}:
        return None
    for arg in argv[1:]:
        if not arg.startswith("-"):
            return arg
    return None


def should_start_scheduler(argv: list[str] | None = None) -> bool:
    """Whether this process should start the in-process reminder scheduler.

    Skipped for tests, migrations, shell, collectstatic, the reminder/expiry
    management commands, and the autoreloader parent process of ``runserver``
    (the child process has ``RUN_MAIN=true`` and is the one that serves).
    WSGI/ASGI servers such as gunicorn have no management subcommand and start
    the scheduler; the database lease keeps only one leader active.
    """
    if not getattr(settings, "REMINDER_SCHEDULER_ENABLED", True):
        return False

    args = list(argv if argv is not None else sys.argv)
    command = _management_command(args)

    if command is not None:
        if command != "runserver":
            return False
        # ``runserver`` with autoreload: the parent process only watches files
        # and must not run a scheduler. ``--noreload`` has no parent.
        if os.environ.get("RUN_MAIN") != "true" and "--noreload" not in args:
            return False

    if "test" in args:
        return False
    if "pytest" in os.path.basename(args[0]).lower():
        return False
    return True


def acquire_lease(owner: str, *, now=None, lease_seconds: int | None = None) -> bool:
    """Try to become (or stay) the active scheduler leader."""
    now = now or timezone.now()
    seconds = lease_seconds or getattr(
        settings, "REMINDER_SCHEDULER_LEASE_SECONDS", 180
    )
    expires_at = now + timedelta(seconds=seconds)

    try:
        updated = (
            ReminderSchedulerLease.objects.filter(name=LEASE_NAME)
            .filter(Q(owner=owner) | Q(expires_at__lte=now))
            .update(owner=owner, expires_at=expires_at, updated_at=now)
        )
        if updated:
            return True
        try:
            # The nested atomic block contains the unique-name IntegrityError
            # so losing the creation race never breaks an outer transaction.
            with transaction.atomic():
                ReminderSchedulerLease.objects.create(
                    name=LEASE_NAME, owner=owner, expires_at=expires_at
                )
            return True
        except IntegrityError:
            # Another worker created/renewed the lease first.
            return False
    except Exception:  # noqa: BLE001 — scheduler must never crash the app
        logger.exception("Reminder scheduler could not acquire its database lease.")
        return False


def renew_lease(owner: str, *, now=None, lease_seconds: int | None = None) -> bool:
    """Extend an already-held lease. Returns False when it is no longer ours."""
    now = now or timezone.now()
    seconds = lease_seconds or getattr(
        settings, "REMINDER_SCHEDULER_LEASE_SECONDS", 180
    )
    expires_at = now + timedelta(seconds=seconds)
    try:
        return bool(
            ReminderSchedulerLease.objects.filter(
                name=LEASE_NAME, owner=owner
            ).update(expires_at=expires_at, updated_at=now)
        )
    except Exception:  # noqa: BLE001
        logger.exception("Reminder scheduler could not renew its database lease.")
        return False


def release_lease(owner: str) -> None:
    """Give up the lease immediately (used on graceful shutdown)."""
    try:
        ReminderSchedulerLease.objects.filter(name=LEASE_NAME, owner=owner).update(
            owner="", expires_at=timezone.now()
        )
    except Exception:  # noqa: BLE001
        pass


def run_sweep_once() -> dict:
    """Run one reminder sweep; imported lazily so Django is fully initialized."""
    from reservations.services import reminders

    return reminders.send_due_reminders()


def run_loop(
    owner: str,
    *,
    interval_seconds: int | None = None,
    initial_delay_seconds: int | None = None,
    poll_seconds: int | None = None,
) -> None:
    """Leader-election loop used by both the thread and the management command."""
    interval = interval_seconds or getattr(
        settings, "REMINDER_SCHEDULER_INTERVAL_SECONDS", 3600
    )
    initial_delay = initial_delay_seconds
    if initial_delay is None:
        initial_delay = getattr(settings, "REMINDER_SCHEDULER_INITIAL_DELAY_SECONDS", 10)
    poll = poll_seconds or getattr(settings, "REMINDER_SCHEDULER_POLL_SECONDS", 60)
    poll = max(1, min(poll, interval))

    next_sweep = time.monotonic() + max(0, initial_delay)
    logger.info(
        "Reminder scheduler loop started (owner=%s, interval=%ss, poll=%ss).",
        owner,
        interval,
        poll,
    )

    while not _stop_event.is_set():
        now_mono = time.monotonic()

        if now_mono >= next_sweep:
            if acquire_lease(owner):
                try:
                    summary = run_sweep_once()
                    logger.info(
                        "Scheduled reminder check complete: %s sent, %s skipped, "
                        "%s failed.",
                        summary.get("sent", 0),
                        summary.get("skipped", 0),
                        summary.get("failed", 0),
                    )
                except Exception:  # noqa: BLE001 — keep the scheduler alive
                    logger.exception(
                        "Scheduled reminder check crashed; it will run again "
                        "at the next interval."
                    )
                next_sweep = time.monotonic() + interval
        else:
            # Stay leader between sweeps. If the lease is gone, try to take it
            # back (or acquire it for the first time after another worker died).
            if not renew_lease(owner):
                acquire_lease(owner)

        _stop_event.wait(poll)


def start_scheduler() -> bool:
    """Start the background thread once per process. Returns True if started."""
    global _started
    with _start_lock:
        if _started:
            return False
        if not should_start_scheduler():
            logger.debug(
                "Reminder scheduler not started for this process (disabled or "
                "running as a management command/test)."
            )
            return False

        _started = True
        _stop_event.clear()
        owner = f"{os.getpid()}-{uuid.uuid4().hex[:12]}"
        thread = threading.Thread(
            target=run_loop,
            args=(owner,),
            name="sas-reminder-scheduler",
            daemon=True,
        )
        thread.start()
        logger.info(
            "Automatic reservation reminder scheduler started "
            "(every %ss, owner=%s).",
            getattr(settings, "REMINDER_SCHEDULER_INTERVAL_SECONDS", 3600),
            owner,
        )
        def _shutdown():
            _stop_event.set()
            release_lease(owner)

        atexit.register(_shutdown)
        return True


def stop_scheduler() -> None:
    """Ask the in-process scheduler to stop (used by tests and shutdown)."""
    _stop_event.set()
