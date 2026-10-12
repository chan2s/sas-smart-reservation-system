"""Unauthenticated reachability probe for the frontend's offline layer.

The PWA must not treat ``navigator.onLine`` as proof that Django is reachable.
This view answers "is the API reachable?" cheaply and predictably:

* plain Django view — no DRF authentication/permission classes, so it can never
  return a 401/429 and be mistaken for an outage or a session problem;
* no database access — reachability is about the service answering, and a slow
  or cold database must not make an otherwise reachable API look down;
* GET only.

It intentionally exposes no application data.
"""

from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET


@require_GET
@never_cache
def health(request):
    return JsonResponse({"status": "ok"})
