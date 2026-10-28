import uuid
from datetime import timedelta

from django.db import models
from django.db.models import Q
from django.utils import timezone

class RobotStatus(models.TextChoices):
    OFFLINE = "offline", "Офлайн"
    IDLE = "idle", "Свободен"
    BUSY = "busy", "Занят"
    PAUSED = "paused", "На паузе"
    STOPPING = "stopping", "Останавливается"


class CommandType(models.TextChoices):
    STOP = "stop", "Остановить"
    KILL = "kill", "Убить"
    RESTART = "restart", "Перезапустить"
    PAUSE = "pause", "Пауза"
    RESUME = "resume", "Продолжить"
    CANCEL_JOB = "cancel_job", "Отменить задание"
    RELOAD_CONFIG = "reload_config", "Перечитать конфиг"
    PING = "ping", "Пинг"


class CommandStatus(models.TextChoices):
    AWAITING_APPROVAL = "awaiting_approval", "Ждёт подтверждения"
    PENDING = "pending", "Ожидает"
    SENT = "sent", "Отправлена"
    ACKNOWLEDGED = "acknowledged", "Получена"
    DONE = "done", "Выполнена"
    FAILED = "failed", "Ошибка"
    EXPIRED = "expired", "Истекла"


def default_command_expiry():
    return timezone.now() + timedelta(minutes=5)


class Robot(models.Model):
    # db_index=False: team_id покрыт уникальным ограничением (team, name)
    team = models.ForeignKey(
        "accounts.Team", on_delete=models.PROTECT, related_name="robots", db_index=False
    )
    name = models.TextField()
    robot_type = models.TextField()
    status = models.TextField(choices=RobotStatus.choices, default=RobotStatus.OFFLINE)
    host = models.TextField(null=True, blank=True)
    api_key_hash = models.CharField(
        max_length=64, unique=True, null=True, blank=True, editable=False
    )
    last_heartbeat_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "robots"
        constraints = [
            models.UniqueConstraint(fields=["team", "name"], name="robots_team_name_uniq"),
            models.CheckConstraint(
                condition=Q(status__in=RobotStatus.values), name="robots_status_valid"
            ),
        ]

    def __str__(self):
        return self.name


class Command(models.Model):
    robot = models.ForeignKey(Robot, on_delete=models.CASCADE, related_name="commands")
    command_type = models.TextField(choices=CommandType.choices)
    status = models.TextField(choices=CommandStatus.choices, default=CommandStatus.PENDING)
    payload = models.JSONField(default=dict)
    idempotency_key = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    created_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="commands"
    )
    created_via_agent = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(default=default_command_expiry)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "commands"
        constraints = [
            models.CheckConstraint(
                condition=Q(command_type__in=CommandType.values), name="commands_type_valid"
            ),
            models.CheckConstraint(
                condition=Q(status__in=CommandStatus.values), name="commands_status_valid"
            ),
        ]
        indexes = [
            models.Index(
                fields=["robot"],
                condition=Q(status__in=[CommandStatus.PENDING, CommandStatus.SENT]),
                name="commands_robot_pending_idx",
            ),
        ]

    def __str__(self):
        return f"{self.command_type} → {self.robot_id}"