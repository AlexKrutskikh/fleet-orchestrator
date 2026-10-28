from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounts.models import TeamRole
from common.mixins import TeamScopedQuerysetMixin
from common.permissions import HasTeamRole

from .models import Job, JobStatus
from .serializers import JobSerializer


class JobViewSet(
    TeamScopedQuerysetMixin,
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    queryset = (
        Job.objects
        .select_related("team")
        .prefetch_related("runs__robot")
        .order_by("-created_at")
    )
    serializer_class = JobSerializer
    permission_classes = [IsAuthenticated, HasTeamRole]
    filterset_fields = ["status", "job_type", "team"]

    required_roles = {
        "list": TeamRole.VIEWER,
        "retrieve": TeamRole.VIEWER,
        "cancel": TeamRole.OPERATOR,
    }

    def get_team_id(self, obj):
        return obj.team_id

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        job = self.get_object()
        cancelled = Job.objects.filter(pk=job.pk, status=JobStatus.PENDING).update(
            status=JobStatus.CANCELLED
        )
        if not cancelled:
            return Response(
                {"detail": "Отменить можно только ожидающее задание."},
                status=status.HTTP_409_CONFLICT,
            )
        job.refresh_from_db()
        return Response(self.get_serializer(job).data)