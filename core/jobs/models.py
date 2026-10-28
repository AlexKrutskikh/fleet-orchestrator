from django.db import models
from django.db.models import F, Q
from django.utils import timezone


class JobStatus(models.TextChoices):
    PENDING = "pending", "Ожидает"
    RUNNING = "running", "Выполняется"
    SUCCEEDED = "succeeded", "Успешно"
    FAILED = "failed", "Ошибка"
    CANCELLED = "cancelled", "Отменено"


class RunStatus(models.TextChoices):
    RUNNING = "running", "Выполняется"
    SUCCEEDED = "succeeded", "Успешно"
    FAILED = "failed", "Ошибка"
    TIMEOUT = "timeout", "Таймаут"
    CANCELLED = "cancelled", "Отменено"


class Job(models.Model):
    team = models.ForeignKey("accounts.Team", on_delete=models.PROTECT, related_name="jobs")
    created_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="jobs"
    )
    job_type = models.TextField()
    payload = models.JSONField(default=dict)
    priority = models.SmallIntegerField(default=5)
    status = models.TextField(choices=JobStatus.choices, default=JobStatus.PENDING)
    max_attempts = models.SmallIntegerField(default=3)
    scheduled_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "jobs"
        constraints = [
            models.CheckConstraint(
                condition=Q(status__in=JobStatus.values), name="jobs_status_valid"
            ),
            models.CheckConstraint(
                condition=Q(priority__gte=1, priority__lte=10), name="jobs_priority_range"
            ),
            models.CheckConstraint(
                condition=Q(max_attempts__gt=0), name="jobs_max_attempts_positive"
            ),
        ]
        indexes = [
            models.Index(
                fields=["-priority", "scheduled_at"],
                condition=Q(status=JobStatus.PENDING),
                name="jobs_queue_idx",
            ),
        ]

    def __str__(self):
        return f"{self.job_type} #{self.pk}"


class Run(models.Model):
    # db_index=False: job_id покрыт уникальным ограничением (job, attempt)
    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name="runs", db_index=False)
    robot = models.ForeignKey(
        "robots.Robot", on_delete=models.SET_NULL, null=True, blank=True, related_name="runs"
    )
    attempt = models.SmallIntegerField()
    status = models.TextField(choices=RunStatus.choices, default=RunStatus.RUNNING)
    started_at = models.DateTimeField(default=timezone.now)
    finished_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "runs"
        constraints = [
            models.UniqueConstraint(fields=["job", "attempt"], name="runs_job_attempt_uniq"),
            models.CheckConstraint(condition=Q(attempt__gt=0), name="runs_attempt_positive"),
            models.CheckConstraint(
                condition=Q(status__in=RunStatus.values), name="runs_status_valid"
            ),
            models.CheckConstraint(
                condition=Q(finished_at__isnull=True) | Q(finished_at__gte=F("started_at")),
                name="runs_finished_after_started",
            ),
        ]

    def __str__(self):
        return f"Run {self.job_id}/{self.attempt}"