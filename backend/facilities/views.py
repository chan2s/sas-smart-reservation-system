from rest_framework import viewsets

from accounts.permissions import IsSasStaffOrReadOnly

from .models import Facility
from .serializers import FacilitySerializer


class FacilityViewSet(viewsets.ModelViewSet):
    queryset = Facility.objects.prefetch_related("operating_hours").all()
    serializer_class = FacilitySerializer
    permission_classes = [IsSasStaffOrReadOnly]
    pagination_class = None
    search_fields = ("name", "location", "description")
    filterset_fields = ("facility_type", "status", "is_active")

    def get_queryset(self):
        qs = super().get_queryset()
        facility_type = self.request.query_params.get("type")
        if facility_type:
            qs = qs.filter(facility_type=facility_type)
        status = self.request.query_params.get("status")
        if status:
            qs = qs.filter(status=status)
        return qs