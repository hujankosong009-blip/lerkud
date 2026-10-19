import hashlib
import re
import secrets
import uuid
from datetime import timedelta
from django.conf import settings
from django.core.exceptions import ValidationError, PermissionDenied
from django.db import transaction
from django.db.models import Max
from django.utils import timezone
from .models import *
from .access import require_case, require_owner, require_coordinator, assignments

FIELDS = [('nik','NIK'),('name','Nama'),('phone','No Telepon'),('address','Alamat'),('city','Kota'),('district','Kecamatan'),('village','Kelurahan'),('rt','RT'),('rw','RW')]
SUCCESS = 'TERIMA KASIH TELAH MELAKUKAN REGISTRASI SELANJUTNYA SILAHKAN MELAKUKAN SKRINING'
SCREEN_PROMPT = 'Silakan ceritakan kendala atau permasalahan terkait narkotika yang Anda alami atau yang ingin Anda konsultasikan. Informasi ini membantu petugas memahami kebutuhan awal Anda.'
SCREEN_THANKS = 'Terima kasih. Informasi Anda telah diterima dan menunggu tindak lanjut petugas. Anda dapat memantau perkembangannya melalui menu Progres Permohonan Saya.'
SELF_MESSAGE = 'Fitur Self Asesmen sedang disiapkan. Untuk menyampaikan kendala atau permasalahan Anda, silakan gunakan menu Skrining.'
TRANSITIONS = {
    Status.WAIT_SCREEN: {Status.CANCELLED},
    Status.WAIT_VERIFY: {Status.REVIEW, Status.CANCELLED},
    Status.REVIEW: {Status.NEED_INFO, Status.FOLLOWUP, Status.CANCELLED},
    Status.NEED_INFO: {Status.CANCELLED},
    Status.FOLLOWUP: {Status.NEED_INFO, Status.DONE, Status.CANCELLED},
    Status.DONE: set(), Status.CANCELLED: set(),
}

def digest(value): return hashlib.sha256(value.encode()).hexdigest()

def validate_field(field, value):
    value = str(value).strip()
    if not value or len(value) > (1000 if field == 'address' else 150):
        raise ValidationError('Isian wajib diisi dan panjangnya harus sesuai.')
    if field == 'nik' and not re.fullmatch(r'[0-9]{16}', value):
        raise ValidationError('NIK harus 16 digit. Pemeriksaan format ini bukan verifikasi Dukcapil.')
    if field in ('rt','rw') and not re.fullmatch(r'[0-9]{1,5}', value):
        raise ValidationError('RT/RW harus berupa angka, maksimal 5 digit. Nol di depan dipertahankan.')
    if field == 'phone':
        value = re.sub(r'[\s().-]', '', value)
        if value.startswith('0'): value = '+62' + value[1:]
        elif value.startswith('62'): value = '+' + value
        if not re.fullmatch(r'\+[1-9][0-9]{7,14}', value):
            raise ValidationError('Gunakan nomor telepon yang valid, misalnya format 08… atau +62….')
    return value

def validate_identity(data):
    return {key:validate_field(key, data.get(key, '')) for key,_ in FIELDS}

def audit(actor, action, obj=''):
    Audit.objects.create(actor=str(actor), action=action, object_id=str(obj))

def active_application(user):
    return Application.objects.filter(applicant__user=user).exclude(status__in=CLOSED).first()

def queue_event(application, event, marker):
    recipients = {application.applicant.user_id}
    admin_assignments = OfficerAssignment.objects.filter(active=True, officer__verified=True, officer__telegram__isnull=False, location__active=True)
    if application.location_id:
        admin_assignments = admin_assignments.filter(models.Q(location_id=application.location_id, role=Role.LOCAL) | models.Q(role=Role.COORD))
    else:
        admin_assignments = admin_assignments.filter(role=Role.COORD)
    recipients.update(admin_assignments.values_list('officer__telegram_id', flat=True))
    for recipient in recipients:
        Notification.objects.get_or_create(dedupe_key=f'{marker}:{recipient}', defaults={'application':application,'recipient_id':recipient,'event':event,'channel':settings.NOTIFICATION_CHANNEL})

@transaction.atomic
def submit_registration(user):
    TelegramUser.objects.select_for_update().get(pk=user.pk)
    existing = active_application(user)
    if existing: return existing, False
    draft = RegistrationDraft.objects.select_for_update().get(user=user)
    if draft.form_status != 'DRAFT_REGISTRASI':
        raise ValidationError('Mulai formulir baru melalui menu registrasi.')
    terms = Terms.objects.filter(active=True).first()
    consent = Consent.objects.filter(user=user, terms=terms).first() if terms else None
    if not consent: raise ValidationError('Baca dan setujui ketentuan yang berlaku terlebih dahulu.')
    data = validate_identity(draft.data)
    profile, _ = Profile.objects.get_or_create(user=user)
    profile.data = data
    profile.address_verified = False
    profile.save()
    duplicate = Application.objects.exclude(applicant=profile).filter(identity__nik=data['nik']).exists()
    app = Application.objects.create(number=f'SM-{timezone.localdate().year}-{uuid.uuid4().hex[:16].upper()}', applicant=profile, identity=data, consent=consent, duplicate_review=duplicate)
    draft.form_status = 'REGISTRASI_TERKIRIM'
    draft.save()
    progress = Progress.objects.create(application=app,new_status=app.status,reason='Registrasi dikirim',public_text='Registrasi diterima. Silakan melengkapi Skrining.')
    audit(f'telegram:{user.pk}', 'registration.submitted', app.pk)
    queue_event(app,'registration',f'progress:{progress.pk}')
    return app, True

@transaction.atomic
def submit_screening(user, application, text):
    app = Application.objects.select_for_update().get(pk=application.pk)
    require_owner(user, app)
    text = text.strip()
    if not text or len(text)>12000: raise ValidationError('Uraian wajib diisi, maksimal 12.000 karakter.')
    if app.status not in [Status.WAIT_SCREEN, Status.NEED_INFO]:
        raise ValidationError('Skrining sudah dikirim atau tahap ini belum tersedia.')
    version = (app.screenings.aggregate(v=Max('version'))['v'] or 0) + 1
    Screening.objects.create(application=app,version=version,text=text)
    old = app.status
    app.status = Status.WAIT_VERIFY
    app.updated_at = timezone.now()
    if not app.location_id:
        rule = RoutingRule.objects.filter(active=True,location__active=True,city__iexact=app.identity['city'],district__iexact=app.identity['district'],village__iexact=app.identity['village']).first()
        if rule:
            app.location = rule.location
            AssignmentHistory.objects.create(application=app,new_location=rule.location,reason='Aturan wilayah terkonfigurasi')
    app.save()
    p = Progress.objects.create(application=app,old_status=old,new_status=app.status,reason='Skrining/kelengkapan dikirim pemohon',public_text='Informasi diterima dan menunggu tindak lanjut petugas.')
    audit(f'telegram:{user.pk}', 'screening.submitted', app.pk)
    queue_event(app,'screening',f'progress:{p.pk}')
    return app

@transaction.atomic
def update_progress(officer, application, new_status, reason, public_text='', internal_text='', reopen=False, expected_status=None):
    app = Application.objects.select_for_update().get(pk=application.pk)
    require_case(officer, app)
    if expected_status is not None and app.status != expected_status:
        raise ValidationError('Permohonan sudah diperbarui. Muat ulang sebelum menyimpan.')
    reason = reason.strip()
    if not reason: raise ValidationError('Alasan/catatan wajib diisi.')
    old = app.status
    if reopen:
        require_coordinator(officer)
        if old not in CLOSED or new_status != Status.REVIEW:
            raise ValidationError('Pembukaan kembali hanya menuju tahap ditinjau.')
        if Application.objects.filter(applicant=app.applicant).exclude(pk=app.pk).exclude(status__in=CLOSED).exists():
            raise ValidationError('Pemohon sudah memiliki permohonan aktif lain.')
    elif new_status != old and new_status not in TRANSITIONS.get(old, set()):
        raise ValidationError('Transisi status tidak diizinkan.')
    app.status = new_status
    app.updated_at = timezone.now()
    app.save()
    p = Progress.objects.create(application=app,old_status=old,new_status=new_status,actor=officer,reason=reason,public_text=public_text.strip())
    if internal_text.strip(): InternalNote.objects.create(application=app,actor=officer,text=internal_text.strip())
    audit(f'officer:{officer.pk}', 'progress.updated', app.pk)
    queue_event(app, 'closed' if new_status in CLOSED else 'progress', f'progress:{p.pk}')
    return app

@transaction.atomic
def assign_application(officer, application, location, reason, responsible=None):
    app = Application.objects.select_for_update().get(pk=application.pk)
    require_coordinator(officer)
    if not reason.strip() or not location.active: raise ValidationError('Lokasi aktif dan alasan wajib diisi.')
    if responsible and not assignments(responsible).filter(location=location,role__in=[Role.LOCAL,Role.COORD]).exists():
        raise ValidationError('Petugas tidak memiliki penugasan aktif pada lokasi ini.')
    old = app.location
    app.location = location
    app.responsible = responsible
    app.updated_at = timezone.now()
    app.save()
    h = AssignmentHistory.objects.create(application=app,old_location=old,new_location=location,officer=officer,reason=reason.strip())
    audit(f'officer:{officer.pk}', 'assignment.changed', app.pk)
    queue_event(app,'assignment',f'assignment:{h.pk}')
    # Notify previous location as well; message contains no applicant details.
    if old and old.pk != location.pk:
        for member in OfficerAssignment.objects.filter(location=old,active=True,officer__verified=True,officer__telegram__isnull=False):
            Notification.objects.get_or_create(dedupe_key=f'assignment-old:{h.pk}:{member.officer.telegram_id}',defaults={'application':app,'recipient':member.officer.telegram,'event':'assignment','channel':settings.NOTIFICATION_CHANNEL})
    return app

@transaction.atomic
def create_activation(location, role, hours=24):
    if role not in Role.values or not location.active or not 1 <= hours <= 168:
        raise ValidationError('Peran, lokasi aktif, dan masa berlaku 1–168 jam diperlukan.')
    raw = secrets.token_urlsafe(32)
    code = ActivationCode.objects.create(digest=digest(raw),location=location,role=role,expires_at=timezone.now()+timedelta(hours=hours))
    return raw, code

@transaction.atomic
def activate(user, raw):
    TelegramUser.objects.select_for_update().get(pk=user.pk)
    cutoff = timezone.now()-timedelta(minutes=15)
    if ActivationAttempt.objects.filter(user=user,at__gte=cutoff,success=False).count()>=5:
        return False
    code = ActivationCode.objects.select_for_update().filter(digest=digest(raw.strip()),used_at__isnull=True,revoked=False,expires_at__gt=timezone.now(),location__active=True).first()
    ActivationAttempt.objects.create(user=user,success=bool(code))
    audit(f'telegram:{user.pk}', 'activation.success' if code else 'activation.failed')
    if not code: return False
    officer, _ = Officer.objects.get_or_create(telegram=user)
    officer.verified = True
    officer.save()
    OfficerAssignment.objects.update_or_create(officer=officer,location=code.location,role=code.role,defaults={'active':True})
    code.used_at = timezone.now()
    code.used_by = user
    code.save()
    return True

@transaction.atomic
def create_recipient_link(user):
    RecipientLink.objects.filter(user=user,used_at__isnull=True).update(expires_at=timezone.now())
    raw = secrets.token_urlsafe(24)
    RecipientLink.objects.create(user=user,digest=digest(raw),expected_sender_id=user.telegram_id,expires_at=timezone.now()+timedelta(minutes=10))
    return raw

@transaction.atomic
def verify_recipient_link(raw, sender_id):
    link = RecipientLink.objects.select_for_update().filter(digest=digest(raw),expected_sender_id=sender_id,used_at__isnull=True,expires_at__gt=timezone.now()).first()
    if not link: return False
    NotificationRecipient.objects.update_or_create(user=link.user,defaults={'mtproto_id':sender_id,'verified_at':timezone.now(),'consent_at':timezone.now(),'active':True})
    link.used_at = timezone.now()
    link.save()
    audit(f'telegram:{link.user_id}', 'notification.recipient_verified')
    return True

def public_progress(user, application):
    require_owner(user, application)
    last = application.progress.exclude(public_text='').last()
    fmt = lambda dt: timezone.localtime(dt).strftime('%d/%m/%Y %H:%M WIB')
    lines = [f'Nomor Permohonan: {application.number}',f'Tanggal pengajuan: {fmt(application.submitted_at)}',f'Status: {application.get_status_display()}',f'Lokasi penanganan: {application.location.name if application.location else "Antrean Koordinator BNN"}',f'Pembaruan terakhir: {fmt(application.updated_at)}',f'Tindak lanjut: {last.public_text if last else "Mohon menunggu informasi dari petugas."}', 'Riwayat perkembangan:']
    for p in application.progress.exclude(public_text='').order_by('-at')[:15]:
        lines.append(f'{fmt(p.at)} — {p.get_new_status_display()}: {p.public_text}')
    if application.status == Status.DONE: lines.append('Selesai berarti proses permohonan ditutup sesuai catatan petugas.')
    return '\n'.join(lines)
