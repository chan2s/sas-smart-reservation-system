from django.conf import settings
from django.http import HttpResponseNotFound
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from .health import health

urlpatterns = [
    path("admin/", admin.site.urls),
    # Unauthenticated reachability probe for the PWA offline layer.
    path("api/health/", health, name="health"),
    path("api/auth/", include("accounts.urls")),
    path("api/", include("facilities.urls")),
    path("api/", include("equipment.urls")),
    path("api/", include("reservations.urls")),
    path("api/", include("notifications.urls")),
    path("api/", include("analytics.urls")),
    path("api/", include("chatbot.urls")),
    path("api/", include("approval_letters.urls")),
]

if settings.DEBUG:
    # Approval-letter artifacts live on the same storage volume as ordinary
    # uploads, but are served only through authenticated API download views.
    # Keep Django's development MEDIA_URL helper from exposing the raw files.
    urlpatterns += [
        path(
            "media/approval_letters/<path:private_path>",
            lambda request, private_path: HttpResponseNotFound(),
        )
    ]
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
