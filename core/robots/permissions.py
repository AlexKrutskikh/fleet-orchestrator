from rest_framework.permissions import BasePermission

from .authentication import RobotPrincipal


class IsRobot(BasePermission):
    def has_permission(self, request, view):
        return isinstance(request.user, RobotPrincipal)