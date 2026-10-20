from django.contrib import admin
from django.core.exceptions import ValidationError
from django import forms
from .models import *
from .access import has_role
from .services import audit

admin.site.site_header = 'SALAM MANIS · Pengelolaan Sistem'
admin.site.site_title = 'SALAM MANIS'
admin.site.index_title = 'Konfigurasi dan akses'

class SystemAdmin(admin.ModelAdmin):
    def allowed(self,request):
        officer=Officer.objects.filter(web_user=request.user,verified=True).first()
        return request.user.is_staff and has_role(officer,Role.SUPERADMIN)
    def has_module_permission(self,request): return self.allowed(request)
    def has_view_permission(self,request,obj=None): return self.allowed(request)
    def has_add_permission(self,request): return self.allowed(request)
    def has_change_permission(self,request,obj=None): return self.allowed(request)
    def has_delete_permission(self,request,obj=None): return False
    def save_model(self,request,obj,form,change):
        super().save_model(request,obj,form,change)
        audit(f'web:{request.user.pk}',f'config.{obj._meta.model_name}.saved',obj.pk)

class TermsForm(forms.ModelForm):
    class Meta:
        model=Terms
        fields='__all__'
    def clean(self):
        data=super().clean()
        if self.instance.pk:
            old=Terms.objects.get(pk=self.instance.pk)
            if data.get('version')!=old.version or data.get('body')!=old.body:
                raise ValidationError('Ketentuan berversi tidak dapat diubah. Buat versi baru; nonaktifkan versi lama sebelum menerbitkannya.')
        return data

@admin.register(Terms)
class TermsAdmin(SystemAdmin):
    form=TermsForm
    list_display=['version','active','published_at']

@admin.register(Location)
class LocationAdmin(SystemAdmin):
    list_display=['name','category','city','active']
    list_filter=['category','active']
    search_fields=['name','city']

@admin.register(OfficerAssignment)
class AssignmentAdmin(SystemAdmin):
    list_display=['officer','location','active']
    list_filter=['active','location']

@admin.register(Officer)
class OfficerAdmin(SystemAdmin):
    readonly_fields=['role','verified']
    exclude=['all_locations']
    list_display=['id','web_user','telegram','role','verified']

@admin.register(ActivationCode)
class CodeAdmin(SystemAdmin):
    list_display=['id','location','role','expires_at','used_at','revoked']
    exclude=['digest']
    readonly_fields=['location','role','expires_at','used_at','used_by']
    def has_add_permission(self,request): return False

@admin.register(RoutingRule)
class RoutingAdmin(SystemAdmin):
    list_display=['city','district','village','location','active']

@admin.register(AssessmentInstrument)
class InstrumentAdmin(SystemAdmin):
    list_display=['name','version','approved_by','approved_at']
    def has_change_permission(self,request,obj=None):
        return super().has_change_permission(request,obj) and not (obj and obj.assessmentresponse_set.exists())

@admin.register(Audit)
class AuditAdmin(SystemAdmin):
    list_display=['at','actor','action','object_id']
    list_filter=['action']
    def has_add_permission(self,request): return False
    def has_change_permission(self,request,obj=None): return False

@admin.register(NotificationRecipient)
class RecipientAdmin(SystemAdmin):
    list_display=['user','verified_at','consent_at','active']
    readonly_fields=['user','mtproto_id','verified_at','consent_at']
    def has_add_permission(self,request): return False
# Case data is deliberately accessed only through the scoped dashboard.

from .views import ThrottledLoginView
admin.site.login = ThrottledLoginView.as_view(extra_context={'title':'Masuk pengelolaan'})
