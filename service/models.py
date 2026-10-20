import uuid
from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone

class Status(models.TextChoices):
    WAIT_SCREEN = 'MENUNGGU_SKRINING', 'Menunggu Skrining'
    WAIT_ASSESS = 'MENUNGGU_SELF_ASESMEN', 'Menunggu Self Asesmen'
    WAIT_PROOF = 'MENUNGGU_BUKTI', 'Menunggu Bukti Self Asesmen'
    WAIT_LOCATION = 'MENUNGGU_TITIK_AKSES', 'Menunggu Pilihan Titik Akses'
    WAIT_VERIFY = 'MENUNGGU_VERIFIKASI', 'Menunggu Verifikasi'
    REVIEW = 'SEDANG_DITINJAU', 'Sedang Ditinjau Petugas'
    NEED_INFO = 'PERLU_KELENGKAPAN', 'Perlu Kelengkapan'
    FOLLOWUP = 'DALAM_TINDAK_LANJUT', 'Dalam Tindak Lanjut'
    DONE = 'SELESAI', 'Selesai'
    CANCELLED = 'DIBATALKAN', 'Dibatalkan'
CLOSED = [Status.DONE, Status.CANCELLED]

class TelegramUser(models.Model):
    telegram_id = models.BigIntegerField(unique=True)
    state = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    bot_notifications = models.BooleanField(default=False)
    notification_decided = models.BooleanField(default=False)
    notification_consent_at = models.DateTimeField(null=True, blank=True)
    def __str__(self): return f'Pengguna #{self.pk}'

class Terms(models.Model):
    version = models.CharField(max_length=50, unique=True)
    body = models.TextField()
    active = models.BooleanField(default=False)
    published_at = models.DateTimeField(default=timezone.now)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['active'], condition=Q(active=True), name='one_active_terms')]
    def __str__(self): return self.version

class Consent(models.Model):
    user = models.ForeignKey(TelegramUser, on_delete=models.PROTECT)
    terms = models.ForeignKey(Terms, on_delete=models.PROTECT)
    accepted_at = models.DateTimeField(default=timezone.now)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['user','terms'], name='consent_version_unique')]

class Profile(models.Model):
    user = models.OneToOneField(TelegramUser, on_delete=models.PROTECT)
    data = models.JSONField(default=dict)
    address_verified = models.BooleanField(default=False)
    def __str__(self): return f'Profil #{self.pk}'

class RegistrationDraft(models.Model):
    user = models.OneToOneField(TelegramUser, on_delete=models.CASCADE)
    data = models.JSONField(default=dict)
    step = models.PositiveSmallIntegerField(default=0)
    form_status = models.CharField(max_length=30, default='DRAFT_REGISTRASI', choices=[('DRAFT_REGISTRASI','Draft'),('REGISTRASI_TERKIRIM','Terkirim')])
    editing = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

class Category(models.TextChoices):
    IPWL='IPWL','IPWL'
    LRKM='LRKM','LRKM'
    LRIP='LRIP','LRIP'
    VILLAGE='KELURAHAN','KELURAHAN'
    POST='POSKO SALAM MANIS','POSKO SALAM MANIS'
    SCHOOL='FASILITAS PENDIDIKAN','FASILITAS PENDIDIKAN'
    LAW='POSBANKUM','POSBANKUM'
    COORD='BNN KOTA SURABAYA','BNN Kota Surabaya (Koordinator)'

class Location(models.Model):
    name = models.CharField(max_length=200)
    category = models.CharField(max_length=30, choices=Category.choices)
    address = models.TextField(blank=True)
    city = models.CharField(max_length=100, blank=True)
    district = models.CharField(max_length=100, blank=True)
    village = models.CharField(max_length=100, blank=True)
    contact = models.CharField(max_length=100, blank=True)
    hours = models.CharField(max_length=200, blank=True)
    map_url = models.URLField(blank=True)
    active = models.BooleanField(default=False)
    ibm_ap = models.TextField(blank=True)
    def __str__(self): return self.name

class Role(models.TextChoices):
    SUPERADMIN='SUPERADMIN','Superadmin'
    PELAKSANA='PELAKSANA','Pelaksana'

class Officer(models.Model):
    web_user = models.OneToOneField(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    telegram = models.OneToOneField(TelegramUser, null=True, blank=True, on_delete=models.PROTECT)
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.PELAKSANA)
    all_locations = models.BooleanField(default=False, verbose_name='Cakupan semua lokasi')
    verified = models.BooleanField(default=False)
    @property
    def operational(self):
        from .access import officer_active
        return officer_active(self)
    def __str__(self):
        return f'{self.web_user.get_username() if self.web_user else "Petugas #"+str(self.pk)} · {self.get_role_display()}'

class OfficerAssignment(models.Model):
    officer = models.ForeignKey(Officer, related_name='assignments', on_delete=models.CASCADE)
    location = models.ForeignKey(Location, on_delete=models.PROTECT)
    active = models.BooleanField(default=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['officer','location'], name='unique_officer_location')]

class ActivationCode(models.Model):
    officer = models.ForeignKey(Officer, null=True, blank=True, on_delete=models.PROTECT)
    digest = models.CharField(max_length=128, unique=True)
    location = models.ForeignKey(Location, on_delete=models.PROTECT)
    role = models.CharField(max_length=10, choices=Role.choices)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    used_by = models.ForeignKey(TelegramUser, null=True, blank=True, on_delete=models.PROTECT)
    revoked = models.BooleanField(default=False)

class ActivationAttempt(models.Model):
    user = models.ForeignKey(TelegramUser, on_delete=models.CASCADE)
    at = models.DateTimeField(default=timezone.now)
    success = models.BooleanField(default=False)

class Application(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    number = models.CharField(max_length=40, unique=True)
    applicant = models.ForeignKey(Profile, on_delete=models.PROTECT)
    identity = models.JSONField()  # Submission identity, separate from profile; authorized edits are audited.
    consent = models.ForeignKey(Consent, on_delete=models.PROTECT)
    status = models.CharField(max_length=30, choices=Status.choices, default=Status.WAIT_SCREEN)
    location = models.ForeignKey(Location, null=True, blank=True, on_delete=models.PROTECT)
    responsible = models.ForeignKey(Officer, null=True, blank=True, on_delete=models.PROTECT)
    duplicate_review = models.BooleanField(default=False)
    legacy_submission = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)
    deleted_by = models.ForeignKey(Officer, related_name='+', null=True, blank=True, on_delete=models.PROTECT)
    delete_reason = models.TextField(blank=True)
    assessment_url = models.URLField(blank=True)
    routed_at = models.DateTimeField(null=True, blank=True)
    location_selected_at = models.DateTimeField(null=True, blank=True)
    submitted_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(default=timezone.now)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['applicant'], condition=Q(deleted_at__isnull=True) & ~Q(status__in=['SELESAI','DIBATALKAN']), name='one_active_application')]
        indexes = [models.Index(fields=['status','updated_at']), models.Index(fields=['location','submitted_at'])]
    def __str__(self): return self.number

class RoutingRule(models.Model):
    city = models.CharField(max_length=100)
    district = models.CharField(max_length=100)
    village = models.CharField(max_length=100)
    location = models.ForeignKey(Location, on_delete=models.PROTECT)
    active = models.BooleanField(default=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['city','district','village'], name='one_route_for_area')]

class Screening(models.Model):
    application = models.ForeignKey(Application, related_name='screenings', on_delete=models.PROTECT)
    version = models.PositiveIntegerField()
    text = models.TextField()
    created_at = models.DateTimeField(default=timezone.now)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['application','version'], name='screen_version_unique')]

class AssignmentHistory(models.Model):
    application = models.ForeignKey(Application, related_name='assignment_history', on_delete=models.PROTECT)
    old_location = models.ForeignKey(Location, related_name='+', null=True, blank=True, on_delete=models.PROTECT)
    new_location = models.ForeignKey(Location, related_name='+', null=True, blank=True, on_delete=models.PROTECT)
    officer = models.ForeignKey(Officer, null=True, on_delete=models.PROTECT)
    reason = models.TextField()
    at = models.DateTimeField(default=timezone.now)

class Progress(models.Model):
    application = models.ForeignKey(Application, related_name='progress', on_delete=models.PROTECT)
    old_status = models.CharField(max_length=30, blank=True)
    new_status = models.CharField(max_length=30, choices=Status.choices)
    actor = models.ForeignKey(Officer, null=True, on_delete=models.PROTECT)
    reason = models.TextField()
    public_text = models.TextField(blank=True)
    at = models.DateTimeField(default=timezone.now)
    class Meta:
        ordering = ['at','pk']

class InternalNote(models.Model):
    application = models.ForeignKey(Application, related_name='notes', on_delete=models.PROTECT)
    actor = models.ForeignKey(Officer, on_delete=models.PROTECT)
    text = models.TextField()
    at = models.DateTimeField(default=timezone.now)

class AssessmentInstrument(models.Model):
    name = models.CharField(max_length=200)
    version = models.CharField(max_length=50)
    questions = models.JSONField(default=list, blank=True)  # Question IDs and explicit answer choices.
    scoring_rules = models.JSONField(default=dict, blank=True)
    consent_text = models.TextField(blank=True)
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT)
    approved_at = models.DateTimeField(null=True, blank=True)
    # v1 deliberately has no activation flag or execution engine.
    class Meta:
        constraints = [models.UniqueConstraint(fields=['name','version'], name='assessment_version_unique')]

class AssessmentResponse(models.Model):
    instrument = models.ForeignKey(AssessmentInstrument, on_delete=models.PROTECT)
    user = models.ForeignKey(TelegramUser, on_delete=models.PROTECT)
    consent_at = models.DateTimeField()
    answers = models.JSONField()
    result = models.JSONField(default=dict)
    created_at = models.DateTimeField(default=timezone.now)

class NotificationRecipient(models.Model):
    user = models.OneToOneField(TelegramUser, on_delete=models.PROTECT)
    mtproto_id = models.BigIntegerField(unique=True)
    verified_at = models.DateTimeField(default=timezone.now)
    consent_at = models.DateTimeField(default=timezone.now)
    active = models.BooleanField(default=True)

class RecipientLink(models.Model):
    user = models.ForeignKey(TelegramUser, on_delete=models.CASCADE)
    digest = models.CharField(max_length=128, unique=True)
    expected_sender_id = models.BigIntegerField()
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True)

class Notification(models.Model):
    application = models.ForeignKey(Application, related_name='notifications', null=True, on_delete=models.PROTECT)
    recipient = models.ForeignKey(TelegramUser, on_delete=models.PROTECT)
    event = models.CharField(max_length=60)
    channel = models.CharField(max_length=10, choices=[('bot','Bot'),('mtproto','Akun institusi')])
    status = models.CharField(max_length=12, default='queued', choices=[('queued','Antre'),('processing','Diproses'),('sent','Terkirim'),('simulated','Simulasi'),('failed','Gagal')])
    queued_at = models.DateTimeField(default=timezone.now)
    sent_at = models.DateTimeField(null=True)
    message_id = models.CharField(max_length=100, blank=True)
    attempts = models.PositiveIntegerField(default=0)
    error = models.CharField(max_length=200, blank=True)
    next_attempt_at = models.DateTimeField(default=timezone.now)
    locked_at = models.DateTimeField(null=True)
    dedupe_key = models.CharField(max_length=160, unique=True)

class Audit(models.Model):
    actor = models.CharField(max_length=100)
    action = models.CharField(max_length=100)
    object_id = models.CharField(max_length=100, blank=True)
    at = models.DateTimeField(default=timezone.now)

class BotUpdate(models.Model):
    update_id = models.BigIntegerField(unique=True)
    replies = models.JSONField(default=list)
    created_at = models.DateTimeField(default=timezone.now)

class RuntimeCursor(models.Model):
    name = models.CharField(max_length=40, unique=True)
    value = models.BigIntegerField(default=0)

class LoginAttempt(models.Model):
    key = models.CharField(max_length=64, db_index=True)
    at = models.DateTimeField(default=timezone.now)

class ScreeningDraft(models.Model):
    application = models.OneToOneField(Application, on_delete=models.CASCADE)
    text = models.TextField()
    updated_at = models.DateTimeField(auto_now=True)


class SiteConfiguration(models.Model):
    title = models.CharField(max_length=80, default='SALAM MANIS')
    subtitle = models.CharField(max_length=160, default='Mendekatkan Akses, Menghubungkan Layanan.')
    description = models.TextField(default='Sadar Lapor Mandiri – Akses Mudah, Aman, Humanis.')
    self_assessment_url = models.URLField(blank=True, verbose_name='Tautan resmi BOSS BNN / Self Asesmen')
    logo = models.BinaryField(null=True, blank=True)
    logo_mime = models.CharField(max_length=30, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    def save(self, *args, **kwargs):
        self.pk = 1
        return super().save(*args, **kwargs)

class AssessmentEvidence(models.Model):
    application = models.ForeignKey(Application, related_name='evidence', on_delete=models.PROTECT)
    image = models.BinaryField()
    mime = models.CharField(max_length=30)
    checksum = models.CharField(max_length=64)
    source_url = models.URLField()
    submitted_at = models.DateTimeField(default=timezone.now)
    consent_at = models.DateTimeField(default=timezone.now)
    submitted_by = models.ForeignKey(Officer, null=True, blank=True, on_delete=models.PROTECT)
    verified_at = models.DateTimeField(null=True, blank=True)
    verified_by = models.ForeignKey(Officer, related_name='+', null=True, blank=True, on_delete=models.PROTECT)
    verification_note = models.TextField(blank=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['application','checksum'], name='unique_evidence_image')]
