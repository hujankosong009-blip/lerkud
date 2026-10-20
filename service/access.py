from django.core.exceptions import PermissionDenied
from django.db.models import Q
from .models import Application, OfficerAssignment, Role, Category


def assignments(officer):
    if not officer or not officer.verified:
        return OfficerAssignment.objects.none()
    return officer.assignments.filter(active=True, location__active=True)


def officer_active(officer):
    if not officer or not officer.verified:
        return False
    if officer.web_user_id and not officer.web_user.is_active:
        return False
    if officer.role == Role.SUPERADMIN:
        return True
    return len(list(assignments(officer).exclude(location__category=Category.COORD).values_list('location_id',flat=True)[:2])) == 1


def has_role(officer, role):
    return officer_active(officer) and officer.role == role


def cases_for(officer, include_deleted=False):
    qs = Application.objects.all()
    if not include_deleted:
        qs = qs.filter(deleted_at__isnull=True)
    if not officer_active(officer):
        return qs.none()
    if officer.role == Role.SUPERADMIN:
        return qs
    location_id=assignments(officer).exclude(location__category=Category.COORD).values_list('location_id',flat=True).first()
    return qs.filter(location_id=location_id,routed_at__isnull=False)


def require_case(officer, application):
    if not cases_for(officer).filter(pk=application.pk).exists():
        raise PermissionDenied('Tidak memiliki akses permohonan.')


def require_owner(user, application):
    if application.applicant.user_id != user.pk or application.deleted_at:
        raise PermissionDenied('Permohonan tidak tersedia.')


def require_coordinator(officer):
    # Backward-compatible service name; the only management role is Superadmin.
    if not has_role(officer, Role.SUPERADMIN):
        raise PermissionDenied('Kewenangan Superadmin diperlukan.')
