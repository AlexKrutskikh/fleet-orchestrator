class TeamScopedQuerysetMixin:
    """Оставляет в queryset только объекты команд, в которых состоит пользователь."""

    team_field = "team"

    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user
        if user.is_superuser:
            return queryset
        return queryset.filter(**{f"{self.team_field}__in": user.teams.values("id")})