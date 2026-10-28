from django.contrib import admin

from .models import Job, Run


class RunInline(admin.TabularInline):
    model = Run
    extra = 0
    autocomplete_fields = ["robot"]


@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    list_display = ["id", "job_type", "team", "status", "priority", "scheduled_at"]
    list_filter = ["status", "job_type", "team"]
    search_fields = ["job_type"]
    list_select_related = ["team"]
    autocomplete_fields = ["team"]
    inlines = [RunInline]


@admin.register(Run)
class RunAdmin(admin.ModelAdmin):
    list_display = ["job", "attempt", "robot", "status", "started_at", "finished_at"]
    list_filter = ["status"]
    list_select_related = ["job", "robot"]
    autocomplete_fields = ["job", "robot"]
