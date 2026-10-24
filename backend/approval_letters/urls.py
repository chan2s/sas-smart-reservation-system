from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
# See facilities/urls.py — the DRF API root at "/api/" is not published.
router.include_root_view = False
router.register("approval-letters", views.ApprovalLetterViewSet, basename="approval-letter")

urlpatterns = router.urls
