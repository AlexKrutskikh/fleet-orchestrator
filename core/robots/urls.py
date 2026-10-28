from rest_framework.routers import DefaultRouter

from .views import RobotViewSet
from .robot_views import RobotAgentViewSet

router = DefaultRouter()
router.register("robots", RobotViewSet, basename="robot")
router.register("robot", RobotAgentViewSet, basename="robot-agent")

urlpatterns = router.urls