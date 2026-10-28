import uuid

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounts.models import TeamRole
from common.mixins import TeamScopedQuerysetMixin
from common.permissions import HasTeamRole

from .models import Command, CommandType, Robot
from .serializers import CommandSerializer, RobotSerializer

from .filters import RobotFilter
from .security import generate_api_key


class RobotViewSet(TeamScopedQuerysetMixin, viewsets.ModelViewSet):
    queryset = Robot.objects.select_related("team").order_by("name")
    serializer_class = RobotSerializer
    permission_classes = [IsAuthenticated, HasTeamRole]
    filterset_class = RobotFilter
    search_fields = ["name", "host"]
    ordering_fields = ["name", "status", "last_heartbeat_at", "created_at"]

    required_roles = {
        "list": TeamRole.VIEWER,
        "retrieve": TeamRole.VIEWER,
        "update": TeamRole.ADMIN,
        "partial_update": TeamRole.ADMIN,
        "destroy": TeamRole.ADMIN,
        "ping": TeamRole.OPERATOR,
        "pause": TeamRole.OPERATOR,
        "resume": TeamRole.OPERATOR,
        "stop": TeamRole.ADMIN,
        "restart": TeamRole.ADMIN,
        "kill": TeamRole.ADMIN,
    }

    def get_team_id(self, obj):
        if isinstance(obj, Command):
            return obj.robot.team_id
        return obj.team_id

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        raw_key, key_hash = generate_api_key()
        serializer.save(api_key_hash=key_hash)
        data = dict(serializer.data)
        data["api_key"] = raw_key  # показываем один раз, больше его нигде не будет
        return Response(data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def ping(self, request, pk=None):
        return self._create_command(CommandType.PING)

    @action(detail=True, methods=["post"])
    def pause(self, request, pk=None):
        return self._create_command(CommandType.PAUSE)

    @action(detail=True, methods=["post"])
    def resume(self, request, pk=None):
        return self._create_command(CommandType.RESUME)

    @action(detail=True, methods=["post"])
    def stop(self, request, pk=None):
        return self._create_command(CommandType.STOP)

    @action(detail=True, methods=["post"])
    def restart(self, request, pk=None):
        return self._create_command(CommandType.RESTART)

    @action(detail=True, methods=["post"])
    def kill(self, request, pk=None):
        return self._create_command(CommandType.KILL)

    def _create_command(self, command_type):
        robot = self.get_object()  # здесь проверяются права на объект
        key = self._get_idempotency_key()

        if key is None:
            command = Command.objects.create(
                robot=robot, command_type=command_type, created_by=self.request.user
            )
            return Response(CommandSerializer(command).data, status=status.HTTP_201_CREATED)

        command, created = Command.objects.get_or_create(
            idempotency_key=key,
            defaults={
                "robot": robot,
                "command_type": command_type,
                "created_by": self.request.user,
            },
        )
        if command.robot_id != robot.id or command.command_type != command_type:
            return Response(
                {"detail": "Этот Idempotency-Key уже использован для другой команды."},
                status=status.HTTP_409_CONFLICT,
            )
        return Response(
            CommandSerializer(command).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

    def _get_idempotency_key(self):
        raw = self.request.headers.get("Idempotency-Key")
        if raw is None:
            return None
        try:
            return uuid.UUID(raw)
        except ValueError:
            raise ValidationError({"Idempotency-Key": "Ожидается UUID."})