from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models import Q


class User(AbstractUser):
    pass


class TeamRole(models.TextChoices):
    VIEWER = "viewer", "Наблюдатель"
    OPERATOR = "operator", "Оператор"
    ADMIN = "admin", "Админ команды"

ROLE_LEVELS = {
    TeamRole.VIEWER: 1,
    TeamRole.OPERATOR: 2,
    TeamRole.ADMIN: 3,
}


class Team(models.Model):
    name = models.TextField(unique=True)
    members = models.ManyToManyField(User, through="TeamMembership", related_name="teams")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "teams"

    def __str__(self):
        return self.name


class TeamMembership(models.Model):
    # db_index=False: user_id покрыт уникальным ограничением (user, team)
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="memberships", db_index=False
    )
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="memberships")
    role = models.TextField(choices=TeamRole.choices, default=TeamRole.VIEWER)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "team_memberships"
        constraints = [
            models.UniqueConstraint(fields=["user", "team"], name="memberships_user_team_uniq"),
            models.CheckConstraint(
                condition=Q(role__in=TeamRole.values), name="memberships_role_valid"
            ),
        ]

    def __str__(self):
        return f"{self.user} в {self.team} ({self.role})"