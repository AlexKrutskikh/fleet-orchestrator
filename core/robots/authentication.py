from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

from .models import Robot
from .security import hash_api_key


class RobotPrincipal:
    """«Пользователь» для запросов от робота. Нужен DRF, чтобы request.user был аутентифицирован."""

    is_authenticated = True
    is_superuser = False
    is_staff = False

    def __init__(self, robot):
        self.robot = robot

    def __str__(self):
        return f"robot:{self.robot.pk}"


class RobotAPIKeyAuthentication(BaseAuthentication):
    keyword = "Robot"

    def authenticate(self, request):
        parts = request.headers.get("Authorization", "").split()
        if len(parts) != 2 or parts[0] != self.keyword:
            return None  # заголовок не нашего формата — пусть пробуют другие классы

        try:
            robot = Robot.objects.select_related("team").get(api_key_hash=hash_api_key(parts[1]))
        except Robot.DoesNotExist:
            raise AuthenticationFailed("Неверный ключ робота.")
        return RobotPrincipal(robot), robot

    def authenticate_header(self, request):
        return self.keyword