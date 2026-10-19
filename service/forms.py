from django import forms
from .models import Status, Location, Officer, Role
from .services import TRANSITIONS
from .access import has_role

class ProgressForm(forms.Form):
    status = forms.ChoiceField(label='Status')
    expected_status = forms.CharField(widget=forms.HiddenInput)
    reason = forms.CharField(label='Alasan / catatan perubahan',widget=forms.Textarea(attrs={'rows':3}),max_length=4000)
    internal_text = forms.CharField(label='Catatan internal (hanya petugas)',required=False,widget=forms.Textarea(attrs={'rows':3}),max_length=12000)
    public_text = forms.CharField(label='Pesan tindak lanjut untuk pemohon',required=False,widget=forms.Textarea(attrs={'rows':3}),max_length=4000)
    reopen = forms.BooleanField(label='Buka kembali dengan alasan (koordinator)',required=False)
    def __init__(self,*args,application,officer,**kwargs):
        super().__init__(*args,**kwargs)
        allowed = {application.status} | TRANSITIONS[application.status]
        if has_role(officer,Role.COORD) and application.status in (Status.DONE,Status.CANCELLED): allowed.add(Status.REVIEW)
        self.fields['status'].choices=[(key,label) for key,label in Status.choices if key in allowed]
        self.fields['status'].initial=application.status
        self.fields['expected_status'].initial=application.status
        if not has_role(officer,Role.COORD): self.fields.pop('reopen')

class AssignmentForm(forms.Form):
    location = forms.ModelChoiceField(label='Lokasi penanganan',queryset=Location.objects.filter(active=True))
    responsible = forms.ModelChoiceField(label='Petugas penanggung jawab',queryset=Officer.objects.filter(verified=True,assignments__active=True,assignments__role__in=[Role.LOCAL,Role.COORD]).distinct(),required=False)
    reason = forms.CharField(label='Alasan penugasan',widget=forms.Textarea(attrs={'rows':2}),max_length=4000)

class InvitationForm(forms.Form):
    location = forms.ModelChoiceField(label='Lokasi aktif',queryset=Location.objects.filter(active=True))
    role = forms.ChoiceField(label='Peran',choices=Role.choices)
    hours = forms.IntegerField(label='Berlaku (jam)',min_value=1,max_value=168,initial=24)
