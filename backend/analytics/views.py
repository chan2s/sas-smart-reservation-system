from datetime import date

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .services import (
    REPORTS,
    cancellation_rate,
    equipment_utilization,
    export_report,
    facility_utilization,
    most_requested,
    no_show_rate,
    peak_periods,
    report_preview,
    requester_breakdown,
    reservation_trends,
    summary,
)


def _range_params(request):
    start = request.query_params.get("from") or request.query_params.get("start")
    end = request.query_params.get("to") or request.query_params.get("end")
    try:
        start = date.fromisoformat(start) if start else None
    except ValueError:
        start = None
    try:
        end = date.fromisoformat(end) if end else None
    except ValueError:
        end = None
    return start, end


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def analytics_summary(request):
    return Response(summary())


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def analytics_trends(request):
    months = int(request.query_params.get("months", 6))
    return Response(reservation_trends(months))


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def analytics_utilization(request):
    days = int(request.query_params.get("days", 30))
    return Response(
        {
            "facility": facility_utilization(days),
            "equipment": equipment_utilization(),
        }
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def analytics_requester_breakdown(request):
    """Campus vs external reservation usage."""
    try:
        days = int(request.query_params.get("days", 365))
    except (TypeError, ValueError):
        days = 365
    return Response(requester_breakdown(days))


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def analytics_insights(request):
    return Response(
        {
            "cancellation_rate": cancellation_rate(),
            "no_show_rate": no_show_rate(),
            "peak_periods": peak_periods(),
            "most_requested": most_requested(),
        }
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def reports_list(request):
    return Response(REPORTS)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def report_detail(request, slug):
    match = next((r for r in REPORTS if r["slug"] == slug), None)
    if not match:
        return Response(
            {"detail": "Report not found."}, status=status.HTTP_404_NOT_FOUND
        )
    start, end = _range_params(request)
    return Response(
        {
            **match,
            "preview": report_preview(slug, start, end),
            "range": {"from": start.isoformat() if start else None, "to": end.isoformat() if end else None},
        }
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def report_export(request, slug, fmt):
    match = next((r for r in REPORTS if r["slug"] == slug), None)
    if not match:
        return Response(
            {"detail": "Report not found."}, status=status.HTTP_404_NOT_FOUND
        )
    if fmt not in ("csv", "xlsx", "json"):
        return Response(
            {"detail": "Unsupported format."}, status=status.HTTP_400_BAD_REQUEST
        )
    start, end = _range_params(request)
    return export_report(slug, fmt, start, end)