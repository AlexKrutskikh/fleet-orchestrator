import pytest
from django.urls import reverse
from rest_framework import status
from jobs.models import Job, JobStatus


@pytest.mark.django_db
class TestJobCancel:
    def test_cancel_pending_by_operator(self, api_client, operator_membership, pending_job):
        api_client.force_authenticate(user=operator_membership.user)
        url = reverse("job-cancel", kwargs={"pk": pending_job.pk})

        response = api_client.post(url)

        assert response.status_code == status.HTTP_200_OK
        pending_job.refresh_from_db()
        assert pending_job.status == JobStatus.CANCELLED

    def test_cancel_running_by_operator(self, api_client, operator_membership, running_job):
        api_client.force_authenticate(user=operator_membership.user)
        url = reverse("job-cancel", kwargs={"pk": running_job.pk})

        response = api_client.post(url)

        assert response.status_code == status.HTTP_409_CONFLICT
        running_job.refresh_from_db()
        assert running_job.status == JobStatus.RUNNING

    def test_cancel_by_viewer_forbidden(self, api_client, viewer_membership, pending_job):
        api_client.force_authenticate(user=viewer_membership.user)
        url = reverse("job-cancel", kwargs={"pk": pending_job.pk})

        response = api_client.post(url)

        assert response.status_code == status.HTTP_403_FORBIDDEN
        pending_job.refresh_from_db()
        assert pending_job.status == JobStatus.PENDING