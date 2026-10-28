from rest_framework.permissions import BasePermission

from accounts.models import ROLE_LEVELS, TeamMembership


def has_team_role(user, team_id: int, required_role: str) -> bool:
    """Есть ли у пользователя в команде роль не ниже required_role."""
    if user.is_superuser:
        return True
    role = (
        TeamMembership.objects
        .filter(user=user, team_id=team_id)
        .values_list("role", flat=True)
        .first()
    )
    return role is not None and ROLE_LEVELS[role] >= ROLE_LEVELS[required_role]


class HasTeamRole(BasePermission):
    """
    Проверяет роль пользователя в команде объекта.
    Требуемая роль берётся из view.required_roles по имени действия,
    команда объекта — из view.get_team_id(obj).
    """

    message = "Недостаточно прав в команде этого объекта."

    def has_object_permission(self, request, view, obj):
        required_role = view.required_roles.get(view.action)
        if required_role is None:
            return request.user.is_superuser
        return has_team_role(request.user, view.get_team_id(obj), required_role)