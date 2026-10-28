from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import Team, TeamMembership, User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    pass


class TeamMembershipInline(admin.TabularInline):
    model = TeamMembership
    extra = 1
    autocomplete_fields = ["user"]


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ["name", "created_at"]
    search_fields = ["name"]
    inlines = [TeamMembershipInline]