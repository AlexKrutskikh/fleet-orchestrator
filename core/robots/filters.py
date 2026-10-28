from datetime import timedelta

from django.utils import timezone
from django_filters import rest_framework as filters

from .models import Robot, RobotStatus

ONLINE_THRESHOLD = timedelta(minutes=1)


class RobotFilter(filters.FilterSet):
    status = filters.MultipleChoiceFilter(choices=RobotStatus.choices)
    robot_type = filters.CharFilter()
    team = filters.NumberFilter(field_name="team_id")
    heartbeat_after = filters.IsoDateTimeFilter(field_name="last_heartbeat_at", lookup_expr="gte")
    online = filters.BooleanFilter(method="filter_online")

    class Meta:
        model = Robot
        fields = ["status", "robot_type", "team"]

    def filter_online(self, queryset, name, value):
        border = timezone.now() - ONLINE_THRESHOLD
        if value:
            return queryset.filter(last_heartbeat_at__gte=border)
        return queryset.exclude(last_heartbeat_at__gte=border)