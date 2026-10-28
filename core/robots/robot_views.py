from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .authentication import RobotAPIKeyAuthentication
from .models import Command, CommandStatus, Robot
from .permissions import IsRobot
from .serializers import CommandSerializer, CompleteCommandSerializer, HeartbeatSerializer
from rest_framework import status

from jobs.models import Job, JobStatus, Run, RunStatus
from jobs.serializers import FinishRunSerializer
import time

from django.conf import settings

class RobotAgentViewSet(viewsets.ViewSet):
    authentication_classes = [RobotAPIKeyAuthentication]
    permission_classes = [IsRobot]

    def _next_job_naive(self):
        """ТОЛЬКО ДЛЯ ДЕМОНСТРАЦИИ ГОНКИ. Так делать нельзя."""
        job = (
            Job.objects
            .filter(
                team_id=self.robot.team_id,
                job_type=self.robot.robot_type,
                status=JobStatus.PENDING,
            )
            .order_by("-priority", "scheduled_at")
            .first()
        )
        if job is None:
            return Response(status=status.HTTP_204_NO_CONTENT)

        time.sleep(0.02)   # «логика» между чтением и записью: проверки, обращение к другому сервису...
        job.status = JobStatus.RUNNING
        job.save(update_fields=["status"])
        return Response({"job": {"id": job.id}, "naive": True})

    @property
    def robot(self):
        return self.request.auth

    @action(detail=False, methods=["post"])
    def heartbeat(self, request):
        serializer = HeartbeatSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        fields = {"last_heartbeat_at": timezone.now()}
        if "status" in serializer.validated_data:
            fields["status"] = serializer.validated_data["status"]
        Robot.objects.filter(pk=self.robot.pk).update(**fields)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=["get"])
    def commands(self, request):
        with transaction.atomic():
            commands = list(
                Command.objects
                .select_for_update(skip_locked=True)
                .filter(
                    robot=self.robot,
                    status=CommandStatus.PENDING,
                    expires_at__gt=timezone.now(),
                )
                .order_by("created_at")
            )
            Command.objects.filter(pk__in=[c.pk for c in commands]).update(
                status=CommandStatus.SENT
            )
        for command in commands:
            command.status = CommandStatus.SENT
        return Response(CommandSerializer(commands, many=True).data)


    @action(detail=False, methods=["post"], url_path=r"commands/(?P<command_id>\d+)/complete")
    def complete(self, request, command_id=None):
        command = get_object_or_404(Command, pk=command_id, robot=self.robot)
        serializer = CompleteCommandSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        command.status = serializer.validated_data["status"]
        command.completed_at = timezone.now()
        command.save(update_fields=["status", "completed_at"])
        return Response(CommandSerializer(command).data)

    @action(detail=False, methods=["post"], url_path="jobs/next")
    def next_job(self, request):
        if settings.DEBUG and request.query_params.get("mode") == "naive":
            return self._next_job_naive()
        with transaction.atomic():
            job = (
                Job.objects
                .select_for_update(skip_locked=True)
                .filter(
                    team_id=self.robot.team_id,
                    job_type=self.robot.robot_type,
                    status=JobStatus.PENDING,
                    scheduled_at__lte=timezone.now(),
                )
                .order_by("-priority", "scheduled_at")
                .first()
            )
            if job is None:
                return Response(status=status.HTTP_204_NO_CONTENT)

            attempt = job.runs.count() + 1
            run = Run.objects.create(job=job, robot=self.robot, attempt=attempt)
            job.status = JobStatus.RUNNING
            job.save(update_fields=["status"])

        return Response({
            "run_id": run.id,
            "attempt": attempt,
            "job": {"id": job.id, "job_type": job.job_type, "payload": job.payload},
        })

    @action(detail=False, methods=["post"], url_path=r"runs/(?P<run_id>\d+)/finish")
    def finish_run(self, request, run_id=None):
        serializer = FinishRunSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        with transaction.atomic():
            run = get_object_or_404(Run, pk=run_id, robot=self.robot)
            # Порядок блокировок тот же, что в next_job: сначала задание, потом запуск
            job = Job.objects.select_for_update().get(pk=run.job_id)
            run = Run.objects.select_for_update().get(pk=run.pk)

            if run.status != RunStatus.RUNNING:
                return Response(
                    {"detail": "Запуск уже завершён."}, status=status.HTTP_409_CONFLICT
                )

            run.status = serializer.validated_data["status"]
            run.error_message = serializer.validated_data.get("error_message") or None
            run.finished_at = timezone.now()
            run.save(update_fields=["status", "error_message", "finished_at"])

            if run.status == RunStatus.SUCCEEDED:
                job.status = JobStatus.SUCCEEDED
            elif run.attempt < job.max_attempts:
                job.status = JobStatus.PENDING      # попытки остались — снова в очередь
            else:
                job.status = JobStatus.FAILED
            job.save(update_fields=["status"])

        return Response({"run_status": run.status, "job_status": job.status})