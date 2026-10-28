from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from .models import Command, CommandStatus, Robot, RobotStatus

OFFLINE_AFTER = timedelta(minutes=1)


@shared_task
def expire_commands():
    """Помечает просроченными команды, которые так и не были выданы роботу."""
    return Command.objects.filter(
        status__in=[CommandStatus.PENDING, CommandStatus.AWAITING_APPROVAL],
        expires_at__lte=timezone.now(),
    ).update(status=CommandStatus.EXPIRED)


@shared_task
def mark_offline_robots():
    """Переводит в offline роботов, которые давно не присылали heartbeat."""
    border = timezone.now() - OFFLINE_AFTER
    return (
        Robot.objects
        .exclude(status=RobotStatus.OFFLINE)
        .exclude(last_heartbeat_at__gte=border)
        .update(status=RobotStatus.OFFLINE)
    )