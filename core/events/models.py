from django.db import models


class StatusEvent(models.Model):
    event_id = models.UUIDField(unique=True)
    robot = models.ForeignKey(
        "robots.Robot", on_delete=models.CASCADE, related_name="status_events"
    )
    run = models.ForeignKey(
        "jobs.Run", on_delete=models.CASCADE, null=True, blank=True, related_name="status_events"
    )
    event_type = models.TextField()
    payload = models.JSONField(default=dict)
    occurred_at = models.DateTimeField()
    received_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "status_events"
        indexes = [
            models.Index(fields=["robot", "-occurred_at"], name="status_events_robot_time_idx"),
        ]

    def __str__(self):
        return f"{self.event_type} от {self.robot_id}"