from django.contrib import admin

from .models import StatusEvent


@admin.register(StatusEvent)
class StatusEventAdmin(admin.ModelAdmin):
    list_display = ["event_type", "robot", "run", "occurred_at", "received_at"]
    list_filter = ["event_type"]
    list_select_related = ["robot", "run"]
    date_hierarchy = "occurred_at"