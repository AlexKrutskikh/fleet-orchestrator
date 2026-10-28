import pytest
from django.contrib.auth import get_user_model
from accounts.models import Team, TeamMembership, TeamRole
from jobs.models import Job, JobStatus

User = get_user_model()


@pytest.fixture
def user():
    return User.objects.create_user(username="testuser", password="pass12345")


@pytest.fixture
def team():
    return Team.objects.create(name="Test Team")


@pytest.fixture
def viewer_membership(user, team):
    return TeamMembership.objects.create(user=user, team=team, role=TeamRole.VIEWER)


@pytest.fixture
def operator_membership(user, team):
    return TeamMembership.objects.create(user=user, team=team, role=TeamRole.OPERATOR)


@pytest.fixture
def admin_membership(user, team):
    return TeamMembership.objects.create(user=user, team=team, role=TeamRole.ADMIN)


@pytest.fixture
def pending_job(team):
    return Job.objects.create(
        team=team,
        job_type="test_job",
        payload={"key": "value"},
        status=JobStatus.PENDING,
    )


@pytest.fixture
def running_job(team):
    return Job.objects.create(
        team=team,
        job_type="test_job",
        payload={"key": "value"},
        status=JobStatus.RUNNING,
    )


@pytest.fixture
def api_client():
    from rest_framework.test import APIClient
    return APIClient()