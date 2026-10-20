from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.password_validation import validate_password
from .models import Status, Location, Officer, Role, TelegramUser, SiteConfiguration
from .services import TRANSITIONS, FIELDS, validate_field
from .access import has_role

class ProgressForm(forms.Form):
    status = forms.ChoiceField(label='Status perjalanan permohonan')
    expected_status = forms.CharField(widget=forms.HiddenInput)
    reason = forms.CharField(label='Alasan / catatan perubahan',widget=forms.Textarea(attrs={'rows':3}),max_length=4000)
    internal_text = forms.CharField(label='Catatan internal (hanya petugas)',required=False,widget=forms.Textarea(attrs={'rows':3}),max_length=12000)
    public_text = forms.CharField(label='Pesan tindak lanjut untuk pemohon',required=False,widget=forms.Textarea(attrs={'rows':3}),max_length=4000)
    reopen = forms.BooleanField(label='Buka kembali dengan alasan (Superadmin)',required=False)
    def __init__(self,*args,application,officer,**kwargs):
        super().__init__(*args,**kwargs)
        allowed = {application.status} | TRANSITIONS[application.status]
        if not application.legacy_submission and application.status==Status.WAIT_VERIFY:
            allowed.discard(Status.REVIEW)
        if has_role(officer,Role.SUPERADMIN) and application.status in (Status.DONE,Status.CANCELLED):
            allowed.add(Status.REVIEW)
        self.fields['status'].choices=[(key,label) for key,label in Status.choices if key in allowed]
        self.fields['status'].initial=application.status
        self.fields['expected_status'].initial=application.status
        if not has_role(officer,Role.SUPERADMIN):
            self.fields.pop('reopen')

class AssignmentForm(forms.Form):
    location = forms.ModelChoiceField(label='Lokasi penanganan',queryset=Location.objects.filter(active=True))
    responsible = forms.ModelChoiceField(label='Pelaksana penanggung jawab',queryset=Officer.objects.filter(verified=True,role=Role.PELAKSANA),required=False)
    reason = forms.CharField(label='Alasan penugasan',widget=forms.Textarea(attrs={'rows':2}),max_length=4000)

class InvitationForm(forms.Form):
    officer = forms.ModelChoiceField(label='Akun yang ditautkan (disarankan)',queryset=Officer.objects.filter(verified=True),required=False)
    location = forms.ModelChoiceField(label='Lokasi aktif',queryset=Location.objects.filter(active=True))
    role = forms.ChoiceField(label='Peran',choices=Role.choices)
    hours = forms.IntegerField(label='Berlaku (jam)',min_value=1,max_value=168,initial=24)

class IdentityForm(forms.Form):
    reason = forms.CharField(label='Alasan pencatatan / perubahan',max_length=2000,widget=forms.Textarea(attrs={'rows':2}))
    screening = forms.CharField(label='Skrining / kendala (riwayat versi disimpan)',required=False,max_length=12000,widget=forms.Textarea(attrs={'rows':4}))
    expected_updated = forms.CharField(required=False,widget=forms.HiddenInput)
    def __init__(self,*args,creating=False,**kwargs):
        super().__init__(*args,**kwargs)
        if creating:
            self.fields['telegram'] = forms.ModelChoiceField(label='Pemohon Telegram yang sudah menyetujui ketentuan',queryset=TelegramUser.objects.filter(consent__terms__active=True).distinct())
        for key,label in FIELDS:
            self.fields[key] = forms.CharField(label=label,max_length=1000 if key=='address' else 150)
        ordered = (['telegram'] if creating else [])+[key for key,_ in FIELDS]+['screening','reason','expected_updated']
        self.order_fields(ordered)
    def clean(self):
        data = super().clean()
        for key,_ in FIELDS:
            if key in data:
                try:
                    data[key] = validate_field(key,data[key])
                except forms.ValidationError as exc:
                    self.add_error(key,exc)
        return data

class VerificationForm(forms.Form):
    decision = forms.ChoiceField(label='Hasil verifikasi berkas',choices=[('accept','Berkas sesuai'),('reject','Perlu perbaikan / kelengkapan')])
    note = forms.CharField(label='Catatan verifikasi',max_length=4000,widget=forms.Textarea(attrs={'rows':3}))
    public_text = forms.CharField(label='Pesan untuk pemohon',required=False,max_length=4000,widget=forms.Textarea(attrs={'rows':2}))

class EvidenceUploadForm(forms.Form):
    screenshot = forms.FileField(label='Screenshot bukti (JPEG/PNG/WebP, maks. 5 MB)')
    confirm = forms.BooleanField(label='Saya berwenang mencatat bukti ini; bukti tetap membutuhkan verifikasi.')

class BrandingForm(forms.ModelForm):
    logo_upload = forms.FileField(label='Logo baru (JPEG/PNG/WebP)',required=False)
    remove_logo = forms.BooleanField(label='Hapus logo saat ini',required=False)
    class Meta:
        model = SiteConfiguration
        fields = ['title','subtitle','description','self_assessment_url']
        labels = {'title':'Nama dashboard','subtitle':'Keterangan singkat','description':'Deskripsi dashboard'}
        widgets = {'description':forms.Textarea(attrs={'rows':3})}
    def clean_self_assessment_url(self):
        value=self.cleaned_data.get('self_assessment_url','')
        if value and not value.startswith('https://'):
            raise forms.ValidationError('Gunakan tautan resmi HTTPS.')
        return value

class AccountCreateForm(UserCreationForm):
    role = forms.ChoiceField(label='Jenis akun',choices=Role.choices,initial=Role.PELAKSANA)
    locations = forms.ModelMultipleChoiceField(label='Lokasi penugasan',queryset=Location.objects.filter(active=True),required=False)
    all_locations = forms.BooleanField(label='Cakupan semua lokasi',required=False)
    class Meta(UserCreationForm.Meta):
        model = get_user_model()
        fields = ['username','first_name','last_name','email']
    def clean(self):
        data=super().clean()
        if data.get('role')==Role.PELAKSANA and not data.get('all_locations') and not data.get('locations'):
            self.add_error('locations','Pilih lokasi atau cakupan semua lokasi.')
        return data

class AccountEditForm(forms.Form):
    username = forms.CharField(label='Username',max_length=150)
    first_name = forms.CharField(label='Nama depan',required=False,max_length=150)
    last_name = forms.CharField(label='Nama belakang',required=False,max_length=150)
    email = forms.EmailField(required=False)
    role = forms.ChoiceField(label='Jenis akun',choices=Role.choices)
    locations = forms.ModelMultipleChoiceField(label='Lokasi penugasan',queryset=Location.objects.filter(active=True),required=False)
    all_locations = forms.BooleanField(label='Cakupan semua lokasi',required=False)
    active = forms.BooleanField(label='Akun aktif dan terverifikasi',required=False)
    new_password = forms.CharField(label='Password baru (kosongkan jika tetap)',required=False,widget=forms.PasswordInput)
    def __init__(self,*args,officer,**kwargs):
        self.officer=officer
        super().__init__(*args,**kwargs)
    def clean_username(self):
        value=self.cleaned_data['username'].strip()
        get_user_model()._meta.get_field('username').run_validators(value)
        if get_user_model().objects.filter(username=value).exclude(pk=self.officer.web_user_id).exists():
            raise forms.ValidationError('Username sudah digunakan.')
        return value
    def clean_new_password(self):
        value=self.cleaned_data['new_password']
        if value:
            validate_password(value,self.officer.web_user)
        return value
    def clean(self):
        data=super().clean()
        if data.get('active') and data.get('role')==Role.PELAKSANA and not data.get('all_locations') and not data.get('locations'):
            self.add_error('locations','Pilih lokasi atau cakupan semua lokasi.')
        return data
