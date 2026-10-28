from django.contrib import admin

from .models import Command, Robot


@admin.register(Robot)
class RobotAdmin(admin.ModelAdmin):
    list_display = ["name", "team", "robot_type", "status", "last_heartbeat_at"]
    list_filter = ["status", "robot_type", "team"]
    search_fields = ["name", "host"]
    list_select_related = ["team"]
    autocomplete_fields = ["team"]


@admin.register(Command)
class CommandAdmin(admin.ModelAdmin):
    list_display = ["command_type", "robot", "status", "created_by", "created_via_agent", "created_at"]
    list_filter = ["status", "command_type", "created_via_agent"]
    list_select_related = ["robot", "created_by"]
    readonly_fields = ["idempotency_key"]
    autocomplete_fields = ["robot"]
