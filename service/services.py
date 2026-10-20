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
from .access import require_case, require_owner, require_coordinator, assignments, officer_active, has_role

FIELDS = [('nik','NIK'),('name','Nama'),('phone','No Telepon'),('address','Alamat'),('city','Kota'),('district','Kecamatan'),('village','Kelurahan'),('rt','RT'),('rw','RW')]
SUCCESS = 'TERIMA KASIH TELAH MELAKUKAN REGISTRASI SELANJUTNYA SILAHKAN MELAKUKAN SKRINING'
SCREEN_PROMPT = 'Silakan ceritakan kendala atau permasalahan terkait narkotika yang Anda alami atau yang ingin Anda konsultasikan. Informasi ini membantu petugas memahami kebutuhan awal Anda.'
SCREEN_THANKS = 'Terima kasih. Informasi Anda telah diterima dan menunggu tindak lanjut petugas. Anda dapat memantau perkembangannya melalui menu Progres Permohonan Saya.'
SELF_MESSAGE = 'Fitur Self Asesmen sedang disiapkan. Untuk menyampaikan kendala atau permasalahan Anda, silakan gunakan menu Skrining.'
TRANSITIONS = {
    Status.WAIT_SCREEN: {Status.CANCELLED},
    Status.WAIT_ASSESS: {Status.CANCELLED},
    Status.WAIT_PROOF: {Status.CANCELLED},
    Status.WAIT_VERIFY: {Status.REVIEW, Status.NEED_INFO, Status.CANCELLED},
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
    return Application.objects.filter(applicant__user=user, deleted_at__isnull=True).exclude(status__in=CLOSED).first()

def queue_event(application, event, marker):
    recipients = {application.applicant.user_id}
    # Staff receive a complete dossier, not incomplete registration/screening drafts.
    if event not in ('registration', 'screening', 'assessment_started') and (application.legacy_submission or application.evidence.exists()):
        for officer in Officer.objects.filter(verified=True, role=Role.PELAKSANA, telegram__isnull=False).select_related('web_user'):
            if cases_for_notification(officer, application):
                recipients.add(officer.telegram_id)
    for recipient in recipients:
        Notification.objects.get_or_create(dedupe_key=f'{marker}:{recipient}', defaults={'application':application,'recipient_id':recipient,'event':event,'channel':settings.NOTIFICATION_CHANNEL})


def cases_for_notification(officer, application):
    from .access import cases_for
    return cases_for(officer).filter(pk=application.pk).exists()


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
    app.status = Status.WAIT_VERIFY if app.legacy_submission else Status.WAIT_ASSESS
    app.updated_at = timezone.now()
    if not app.location_id:
        rule = RoutingRule.objects.filter(active=True,location__active=True,city__iexact=app.identity['city'],district__iexact=app.identity['district'],village__iexact=app.identity['village']).first()
        if rule:
            app.location = rule.location
            AssignmentHistory.objects.create(application=app,new_location=rule.location,reason='Aturan wilayah terkonfigurasi')
    app.save()
    p = Progress.objects.create(application=app,old_status=old,new_status=app.status,reason='Skrining/kelengkapan dikirim pemohon',public_text='Kendala diterima. Lanjutkan Self Asesmen dan kirim bukti pengisian.' if app.status == Status.WAIT_ASSESS else 'Kelengkapan diterima dan menunggu verifikasi petugas.')
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
        if Application.objects.filter(applicant=app.applicant, deleted_at__isnull=True).exclude(pk=app.pk).exclude(status__in=CLOSED).exists():
            raise ValidationError('Pemohon sudah memiliki permohonan aktif lain.')
    elif new_status != old and new_status not in TRANSITIONS.get(old, set()):
        raise ValidationError('Transisi status tidak diizinkan.')
    if new_status == Status.REVIEW and old not in CLOSED and not app.legacy_submission:
        latest = app.evidence.order_by('-submitted_at', '-pk').first()
        if not latest or not latest.verified_at:
            raise ValidationError('Verifikasi bukti Self Asesmen terlebih dahulu.')
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
    if responsible and (not officer_active(responsible) or responsible.role != Role.PELAKSANA or not (responsible.all_locations or assignments(responsible).filter(location=location).exists())):
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
        for member in OfficerAssignment.objects.filter(location=old,active=True,officer__verified=True,officer__telegram__isnull=False,officer__role=Role.PELAKSANA):
            Notification.objects.get_or_create(dedupe_key=f'assignment-old:{h.pk}:{member.officer.telegram_id}',defaults={'application':app,'recipient':member.officer.telegram,'event':'assignment','channel':settings.NOTIFICATION_CHANNEL})
    return app

@transaction.atomic
def create_activation(location, role, hours=24, officer=None):
    if role not in Role.values or not location.active or not 1 <= hours <= 168:
        raise ValidationError('Peran, lokasi aktif, dan masa berlaku 1–168 jam diperlukan.')
    if officer and (officer.role != role or not officer.verified):
        raise ValidationError('Peran undangan harus sesuai akun petugas terverifikasi.')
    raw = secrets.token_urlsafe(32)
    code = ActivationCode.objects.create(digest=digest(raw),location=location,role=role,officer=officer,expires_at=timezone.now()+timedelta(hours=hours))
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
    existing = Officer.objects.filter(telegram=user).first()
    if code.officer_id:
        officer = Officer.objects.select_for_update().get(pk=code.officer_id)
        if (officer.telegram_id and officer.telegram_id != user.pk) or (existing and existing.pk != officer.pk):
            return False
        if officer.role != code.role or not officer.verified:
            return False
    else:
        officer = existing or Officer(telegram=user)
        # Only a role-bound invitation can change a Telegram-only officer role.
        if existing and existing.web_user_id and existing.role != code.role:
            return False
        officer.role = code.role
    officer.telegram = user
    officer.verified = True
    officer.save()
    OfficerAssignment.objects.update_or_create(officer=officer,location=code.location,defaults={'active':True})
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


def site_config():
    return SiteConfiguration.objects.get_or_create(pk=1)[0]


@transaction.atomic
def begin_assessment(user, application):
    app = Application.objects.select_for_update().get(pk=application.pk)
    require_owner(user, app)
    if not app.screenings.exists():
        raise ValidationError('Lengkapi Skrining/kendala terlebih dahulu.')
    if app.status not in (Status.WAIT_ASSESS, Status.WAIT_PROOF, Status.NEED_INFO):
        raise ValidationError('Tahap unggah bukti belum tersedia untuk permohonan ini.')
    url = site_config().self_assessment_url
    if not url:
        raise ValidationError('Link Self Asesmen belum diisi Superadmin. Kendala Anda sudah tersimpan; silakan kembali setelah link tersedia.')
    from django.core.validators import URLValidator
    URLValidator(schemes=['https'])(url)
    old = app.status
    if old == Status.WAIT_ASSESS:
        app.status = Status.WAIT_PROOF
    app.assessment_url = url
    app.updated_at = timezone.now()
    app.save()
    if old != app.status:
        Progress.objects.create(application=app,old_status=old,new_status=app.status,reason='Tautan asesmen diberikan',public_text='Silakan isi Self Asesmen, lalu kirim bukti screenshot melalui bot.')
    return app


@transaction.atomic
def submit_evidence(user, application, image_data, submitted_by=None):
    from .uploads import clean_image
    app = Application.objects.select_for_update().get(pk=application.pk)
    if submitted_by:
        require_case(submitted_by, app)
    else:
        require_owner(user, app)
    if not app.screenings.exists():
        raise ValidationError('Lengkapi Skrining terlebih dahulu.')
    if not app.assessment_url:
        raise ValidationError('Buka tautan Self Asesmen terlebih dahulu.')
    image, mime, checksum = clean_image(image_data)
    existing = app.evidence.filter(checksum=checksum).first()
    if existing:
        if app.status in (Status.WAIT_PROOF, Status.NEED_INFO):
            raise ValidationError('Screenshot ini sudah pernah dikirim. Unggah bukti baru sesuai permintaan perbaikan atau hubungi Pelaksana.')
        return existing
    if app.status not in (Status.WAIT_PROOF, Status.NEED_INFO):
        raise ValidationError('Bukti sudah dikirim atau tahap unggah belum tersedia.')
    item = AssessmentEvidence.objects.create(application=app,image=image,mime=mime,checksum=checksum,source_url=app.assessment_url,submitted_by=submitted_by)
    old = app.status
    app.status = Status.WAIT_VERIFY
    app.updated_at = timezone.now()
    app.save()
    p = Progress.objects.create(application=app,old_status=old,new_status=app.status,reason='Bukti pengisian dikirim',public_text='Data diri, kendala, dan bukti pengisian diterima. Menunggu verifikasi Pelaksana.')
    audit(f'officer:{submitted_by.pk}' if submitted_by else f'telegram:{user.pk}', 'evidence.submitted', item.pk)
    queue_event(app,'dossier_ready',f'progress:{p.pk}')
    return item


@transaction.atomic
def verify_application(officer, application, accepted, note, public_text=''):
    app = Application.objects.select_for_update().get(pk=application.pk)
    require_case(officer, app)
    if app.status != Status.WAIT_VERIFY:
        raise ValidationError('Permohonan tidak sedang menunggu verifikasi.')
    evidence = app.evidence.order_by('-submitted_at', '-pk').first()
    if not evidence or not note.strip():
        raise ValidationError('Bukti dan catatan verifikasi wajib tersedia.')
    evidence.verification_note = note.strip()
    evidence.verified_at = timezone.now() if accepted else None
    evidence.verified_by = officer
    evidence.save()
    return update_progress(officer,app,Status.REVIEW if accepted else Status.NEED_INFO,note,public_text or ('Berkas telah diverifikasi Pelaksana.' if accepted else 'Mohon lengkapi/kirim ulang bukti melalui bot.'),expected_status=Status.WAIT_VERIFY)


@transaction.atomic
def edit_application(officer, application, identity, reason, screening='', expected_updated=''):
    app = Application.objects.select_for_update().get(pk=application.pk)
    require_case(officer, app)
    if not reason.strip():
        raise ValidationError('Alasan perubahan wajib diisi.')
    if expected_updated and expected_updated != app.updated_at.isoformat():
        raise ValidationError('Data sudah berubah. Muat ulang halaman sebelum mengedit.')
    app.identity = validate_identity(identity)
    app.updated_at = timezone.now()
    app.save()
    if app.status not in CLOSED:
        app.applicant.data = app.identity
        app.applicant.address_verified = False
        app.applicant.save()
    if screening.strip() and (not app.screenings.exists() or app.screenings.order_by('-version').first().text != screening.strip()):
        Screening.objects.create(application=app,version=(app.screenings.aggregate(v=Max('version'))['v'] or 0)+1,text=screening.strip())
    p = Progress.objects.create(application=app,old_status=app.status,new_status=app.status,actor=officer,reason=reason.strip())
    audit(f'officer:{officer.pk}','application.edited',app.pk)
    queue_event(app,'progress',f'progress:{p.pk}')
    return app


@transaction.atomic
def archive_application(officer, application, reason):
    require_coordinator(officer)
    app = Application.objects.select_for_update().get(pk=application.pk)
    require_case(officer, app)
    if not reason.strip():
        raise ValidationError('Alasan penghapusan wajib diisi.')
    old = app.status
    if app.status not in CLOSED:
        app.status = Status.CANCELLED
    app.deleted_at = timezone.now()
    app.deleted_by = officer
    app.delete_reason = reason.strip()
    app.updated_at = timezone.now()
    app.save()
    Progress.objects.create(application=app,old_status=old,new_status=app.status,actor=officer,reason='Diarsipkan: '+reason.strip())
    Notification.objects.filter(application=app,status__in=['queued','failed']).update(status='failed',attempts=5,error='application_archived')
    audit(f'officer:{officer.pk}','application.archived',app.pk)


@transaction.atomic
def restore_application(officer, application):
    require_coordinator(officer)
    app = Application.objects.select_for_update().get(pk=application.pk)
    app.deleted_at = None
    app.deleted_by = None
    app.delete_reason = ''
    app.updated_at = timezone.now()
    app.save()
    audit(f'officer:{officer.pk}','application.restored',app.pk)


@transaction.atomic
def save_account(actor, data, officer=None, new_user=None):
    require_coordinator(actor)
    # Lock the complete active manager set to prevent concurrent last-manager removal.
    managers = list(Officer.objects.select_for_update().filter(role=Role.SUPERADMIN,verified=True,web_user__is_active=True).order_by('pk'))
    if officer:
        officer = Officer.objects.select_for_update().get(pk=officer.pk)
        if not officer.web_user_id:
            raise ValidationError('Akun Telegram ini belum memiliki login web. Buat login baru lalu tautkan melalui undangan yang sesuai.')
        active = data.get('active',False)
        if officer.pk==actor.pk and not active:
            raise ValidationError('Anda tidak dapat menonaktifkan akun sendiri.')
        if officer.role==Role.SUPERADMIN and (not active or data['role']!=Role.SUPERADMIN) and len(managers)<=1:
            raise ValidationError('Minimal satu Superadmin aktif harus dipertahankan.')
        web = officer.web_user
        for key in ('username','first_name','last_name','email'):
            setattr(web,key,data[key])
        if data.get('new_password'):
            web.set_password(data['new_password'])
    else:
        web = new_user
        active = True
        officer = Officer(web_user=web)
    web.is_active = active
    web.is_staff = active and data['role']==Role.SUPERADMIN
    if data['role']!=Role.SUPERADMIN:
        web.is_superuser = False
        web.groups.clear()
        web.user_permissions.clear()
    web.save()
    officer.role = data['role']
    officer.verified = active
    officer.all_locations = data.get('all_locations',False)
    officer.save()
    officer.assignments.update(active=False)
    for location in data.get('locations',[]):
        OfficerAssignment.objects.update_or_create(officer=officer,location=location,defaults={'active':True})
    ActivationCode.objects.filter(officer=officer,used_at__isnull=True).update(revoked=True)
    audit(f'officer:{actor.pk}','account.saved',officer.pk)
    return officer
