from rest_framework import serializers
from accounts.models import TeamMembership, TeamRole
from .models import Command, CommandStatus, Robot, RobotStatus

class RobotSerializer(serializers.ModelSerializer):
    team_name = serializers.CharField(source="team.name", read_only=True)

    class Meta:
        model = Robot
        fields = [
            "id", "name", "team", "team_name", "robot_type",
            "status", "host", "last_heartbeat_at", "created_at",
        ]
        read_only_fields = ["status", "last_heartbeat_at", "created_at"]

    def validate_team(self, team):
        if self.instance is not None and self.instance.team_id != team.id:
            raise serializers.ValidationError("Робота нельзя перенести в другую команду.")

        user = self.context["request"].user
        if user.is_superuser:
            return team

        is_admin = TeamMembership.objects.filter(
            user=user, team=team, role=TeamRole.ADMIN
        ).exists()
        if not is_admin:
            raise serializers.ValidationError("Добавлять роботов может только админ команды.")
        return team



class CommandSerializer(serializers.ModelSerializer):
    class Meta:
        model = Command
        fields = [
            "id", "robot", "command_type", "status", "idempotency_key",
            "created_by", "created_via_agent", "created_at", "expires_at", "completed_at",
        ]
        read_only_fields = fields


class HeartbeatSerializer(serializers.Serializer):
    status = serializers.ChoiceField(
        choices=[RobotStatus.IDLE, RobotStatus.BUSY, RobotStatus.PAUSED, RobotStatus.STOPPING],
        required=False,
    )


class CompleteCommandSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=[CommandStatus.DONE, CommandStatus.FAILED])