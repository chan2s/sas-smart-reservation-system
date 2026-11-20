"""Package-based availability calculations for equipment bundles.

This module handles availability calculation for packages like Sound System Package,
which treat multiple equipment items and services as a single rentable unit.
"""

from __future__ import annotations

from datetime import date as date_cls, time as time_cls
from decimal import Decimal

from django.db.models import Sum

from equipment.models import Equipment, MaintenanceRecord, EquipmentPackage, EquipmentPackageComponent
from equipment.services import facility_resource_limits


def package_availability(
    package_id: int,
    facility_id: int,
    target_date: date_cls,
    start_time: time_cls,
    end_time: time_cls,
    exclude_reservation_id: int | None = None,
) -> dict:
    """Calculate available complete packages for a facility and time window.
    
    A package is only available if ALL required components have sufficient
    inventory given existing reservations and maintenance records.
    
    Args:
        package_id: EquipmentPackage ID
        facility_id: Facility ID (used for facility-specific resource limits)
        target_date: Date of the reservation
        start_time: Reservation start time
        end_time: Reservation end time
        exclude_reservation_id: Reservation to exclude from availability check
        
    Returns:
        {
            "package_id": int,
            "package_name": str,
            "facility_id": int,
            "components": [
                {
                    "equipment_id": int,
                    "equipment_name": str,
                    "total": int,
                    "reserved": int,
                    "under_maintenance": int,
                    "available": int,
                    "required_per_package": int,
                    "available_packages": int,  # Min across all components
                }
            ],
            "available_packages": int,  # Bottleneck (minimum across components)
            "can_reserve": bool,  # True if at least 1 package available
            "problems": [str],  # Human-readable issues
        }
    """
    from reservations.models import Reservation
    from reservations.services.availability import reserved_quantities, maintenance_quantities
    
    package = EquipmentPackage.objects.filter(pk=package_id, is_active=True).first()
    if not package:
        return {
            "package_id": package_id,
            "package_name": "Unknown Package",
            "facility_id": facility_id,
            "components": [],
            "available_packages": 0,
            "can_reserve": False,
            "problems": ["Package not found or inactive"],
        }
    
    # Get reserved and maintenance quantities
    reserved = reserved_quantities(target_date, start_time, end_time, exclude_reservation_id)
    maintenance = maintenance_quantities()
    
    # Get facility-specific resource limits if configured
    limits = facility_resource_limits(facility_id) if facility_id else {}
    
    component_results = []
    min_available_packages = None
    
    for component in package.components.select_related("equipment"):
        equipment = component.equipment
        eq_id = equipment.id
        required_qty = component.quantity_per_package
        
        # Query available inventory for this component
        total_qty = equipment.total_quantity
        reserved_qty = reserved.get(eq_id, 0)
        maintenance_qty = maintenance.get(eq_id, 0)
        
        # Respect equipment status
        if equipment.status != Equipment.Status.AVAILABLE:
            available_qty = 0
        else:
            available_qty = max(total_qty - reserved_qty - maintenance_qty, 0)
            # Apply facility-specific limits if configured
            if facility_id and eq_id in limits:
                available_qty = min(available_qty, limits[eq_id])
        
        # Calculate how many complete packages this component can support
        if required_qty > 0:
            packages_from_component = available_qty // required_qty
        else:
            packages_from_component = 0
        
        component_results.append({
            "equipment_id": eq_id,
            "equipment_name": equipment.name,
            "total": total_qty,
            "reserved": reserved_qty,
            "under_maintenance": maintenance_qty,
            "available": available_qty,
            "required_per_package": required_qty,
            "available_packages": packages_from_component,
        })
        
        # Track minimum (bottleneck)
        if min_available_packages is None:
            min_available_packages = packages_from_component
        else:
            min_available_packages = min(min_available_packages, packages_from_component)
    
    if min_available_packages is None:
        min_available_packages = 0
    
    # Generate human-readable problems
    problems = []
    for component in component_results:
        if component["available_packages"] < 1:
            problems.append(
                f"{component['equipment_name']}: Only {component['available']} available "
                f"(need {component['required_per_package']} per package)"
            )
    
    return {
        "package_id": package_id,
        "package_name": package.name,
        "facility_id": facility_id,
        "components": component_results,
        "available_packages": min_available_packages,
        "can_reserve": min_available_packages > 0,
        "problems": problems,
    }


def operator_availability(
    facility_id: int,
    target_date: date_cls,
    start_time: time_cls,
    end_time: time_cls,
    exclude_reservation_id: int | None = None,
) -> dict:
    """Check availability of Sound System Operators for the requested time window.
    
    Args:
        facility_id: Facility ID (for context only)
        target_date: Date of the reservation
        start_time: Reservation start time
        end_time: Reservation end time
        exclude_reservation_id: Reservation to exclude from availability check
        
    Returns:
        {
            "available_operators": [
                {
                    "operator_id": int,
                    "operator_name": str,
                    "rate": Decimal,
                    "status": str,
                }
            ],
            "has_available_operator": bool,
            "message": str,  # Human-readable status
        }
    """
    from equipment.models import SoundSystemOperator
    from reservations.models import Reservation
    
    # Get all available operators
    available_operators_qs = SoundSystemOperator.objects.filter(
        is_active=True,
        status=SoundSystemOperator.Status.AVAILABLE,
    )
    
    # Check which operators have no conflicting reservations
    available_operators = []
    for operator in available_operators_qs:
        # Get reservations for this operator on the target date with time overlap
        conflicts = Reservation.objects.filter(
            assigned_operator=operator,
            date=target_date,
            status__in=Reservation.AVAILABILITY_BLOCKING_STATUSES,
            start_time__lt=end_time,
            end_time__gt=start_time,
        )
        
        if exclude_reservation_id:
            conflicts = conflicts.exclude(pk=exclude_reservation_id)
        
        # If no conflicts, operator is available
        if not conflicts.exists():
            available_operators.append({
                "operator_id": operator.id,
                "operator_name": operator.name,
                "rate": operator.rate,
                "status": operator.status,
            })
    
    has_available = len(available_operators) > 0
    message = (
        f"{len(available_operators)} operator(s) available"
        if has_available
        else "No operators available for the requested time window"
    )
    
    return {
        "available_operators": available_operators,
        "has_available_operator": has_available,
        "message": message,
    }
