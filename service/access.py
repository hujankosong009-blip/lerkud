from django.core.exceptions import PermissionDenied
from .models import Application, OfficerAssignment, Role

def assignments(officer):
    if not officer or not officer.verified:
        return OfficerAssignment.objects.none()
    return officer.assignments.filter(active=True, location__active=True)

def has_role(officer, role):
    return assignments(officer).filter(role=role).exists()

def cases_for(officer):
    if has_role(officer, Role.COORD):
        return Application.objects.all()
    locations = assignments(officer).filter(role=Role.LOCAL).values('location_id')
    return Application.objects.filter(location_id__in=locations)

def require_case(officer, application):
    if not cases_for(officer).filter(pk=application.pk).exists():
        raise PermissionDenied('Tidak memiliki akses permohonan.')

def require_owner(user, application):
    if application.applicant.user_id != user.pk:
        raise PermissionDenied('Permohonan tidak tersedia.')

def require_coordinator(officer):
    if not has_role(officer, Role.COORD):
        raise PermissionDenied('Kewenangan koordinator diperlukan.')
