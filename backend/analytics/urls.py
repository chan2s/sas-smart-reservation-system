from django.urls import path

from .views import (
    analytics_insights,
    analytics_requester_breakdown,
    analytics_summary,
    analytics_trends,
    analytics_utilization,
    report_detail,
    report_export,
    reports_list,
)

urlpatterns = [
    path("analytics/summary/", analytics_summary, name="analytics-summary"),
    path("analytics/trends/", analytics_trends, name="analytics-trends"),
    path("analytics/utilization/", analytics_utilization, name="analytics-utilization"),
    path(
        "analytics/requester-breakdown/",
        analytics_requester_breakdown,
        name="analytics-requester-breakdown",
    ),
    path("analytics/insights/", analytics_insights, name="analytics-insights"),
    path("reports/", reports_list, name="reports-list"),
    path("reports/<slug:slug>/", report_detail, name="report-detail"),
    path(
        "reports/<slug:slug>/export/<str:fmt>/",
        report_export,
        name="report-export",
    ),
]