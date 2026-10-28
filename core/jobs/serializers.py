from rest_framework import serializers

from accounts.models import TeamRole
from common.permissions import has_team_role

from .models import Job, Run, RunStatus


class RunSerializer(serializers.ModelSerializer):
    robot_name = serializers.CharField(source="robot.name", read_only=True, default=None)

    class Meta:
        model = Run
        fields = [
            "id", "robot", "robot_name", "attempt", "status",
            "started_at", "finished_at", "error_message",
        ]
        read_only_fields = fields


class JobSerializer(serializers.ModelSerializer):
    runs = RunSerializer(many=True, read_only=True)

    class Meta:
        model = Job
        fields = [
            "id", "team", "job_type", "payload", "priority", "status",
            "max_attempts", "scheduled_at", "created_by", "created_at", "runs",
        ]
        read_only_fields = ["status", "created_by", "created_at"]
        extra_kwargs = {
            "priority": {"min_value": 1, "max_value": 10},
            "max_attempts": {"min_value": 1, "max_value": 10},
        }

    def validate_team(self, team):
        if not has_team_role(self.context["request"].user, team.id, TeamRole.OPERATOR):
            raise serializers.ValidationError("Создавать задания может оператор или админ команды.")
        return team


class FinishRunSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=[RunStatus.SUCCEEDED, RunStatus.FAILED])
    error_message = serializers.CharField(required=False, allow_blank=True, max_length=2000)