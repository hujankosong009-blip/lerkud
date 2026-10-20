import hashlib
from datetime import timedelta
from functools import wraps
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.views import LoginView
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db.models import Count
from django.http import HttpResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods
from .models import *
from .access import cases_for, has_role, assignments, officer_active
from .services import update_progress, assign_application, create_activation, audit, FIELDS
from .forms import ProgressForm, AssignmentForm, InvitationForm

class ThrottledLoginView(LoginView):
    template_name='service/login.html'
    def post(self,request,*args,**kwargs):
        # Use the direct peer address; do not trust arbitrary forwarding headers.
        key=hashlib.sha256(request.META.get('REMOTE_ADDR','unknown').encode()).hexdigest()
        attempts=LoginAttempt.objects.filter(key=key,at__gte=timezone.now()-timedelta(minutes=15))
        if attempts.count()>=10: return HttpResponse('Terlalu banyak percobaan. Coba kembali setelah 15 menit.',status=429)
        LoginAttempt.objects.create(key=key)
        return super().post(request,*args,**kwargs)

def officer_for(request):
    officer=Officer.objects.filter(web_user=request.user,verified=True).first()
    if not officer_active(officer): raise PermissionDenied('Akun belum memiliki penugasan terverifikasi dan aktif.')
    return officer

def protected(view):
    @login_required
    @never_cache
    @wraps(view)
    def wrapper(request,*args,**kwargs):
        request.officer=officer_for(request)
        response=view(request,*args,**kwargs)
        response['Referrer-Policy']='same-origin'
        return response
    return wrapper

def context(request,**values):
    return {'is_coordinator':has_role(request.officer,Role.SUPERADMIN),'is_system':has_role(request.officer,Role.SUPERADMIN),'officer':request.officer,**values}

@protected
@require_GET
def overview(request):
    return redirect('applications')

@protected
@require_GET
def applications(request):
    archived=request.GET.get('archived')=='1' and has_role(request.officer,Role.SUPERADMIN)
    qs=cases_for(request.officer,include_deleted=archived).select_related('location','responsible')
    if archived: qs=qs.filter(deleted_at__isnull=False)
    tab=request.GET.get('tab','applicant')
    if tab not in ('applicant','screening','proof'): tab='applicant'
    q=request.GET.get('q','').strip()
    from django.db.models import Q
    if q:
        if tab=='screening': qs=qs.filter(Q(number__icontains=q)|Q(identity__name__icontains=q)|Q(screenings__text__icontains=q)).distinct()
        elif tab=='proof': qs=qs.filter(Q(number__icontains=q)|Q(identity__name__icontains=q)|Q(evidence__verification_note__icontains=q)).distinct()
        else: qs=qs.filter(Q(number__icontains=q)|Q(identity__name__icontains=q)|Q(identity__nik__icontains=q)|Q(identity__phone__icontains=q)|Q(identity__city__icontains=q)).distinct()
    filters={'status':'status','category':'location__category','location':'location_id','city':'identity__city__icontains','district':'identity__district__icontains','village':'identity__village__icontains','responsible':'responsible_id'}
    for param,field in filters.items():
        value=request.GET.get(param,'').strip()
        if not value: continue
        if param in ['location','responsible'] and not value.isdigit(): continue
        qs=qs.filter(**{field:value})
    for param,lookup in [('from','submitted_at__date__gte'),('to','submitted_at__date__lte')]:
        try: date=parse_date(request.GET.get(param,''))
        except ValueError: date=None
        if date: qs=qs.filter(**{lookup:date})
    if request.GET.get('stale')=='1': qs=qs.exclude(status__in=CLOSED).filter(updated_at__lt=timezone.now()-timedelta(days=settings.STALE_DAYS))
    if request.GET.get('unassigned')=='1': qs=qs.filter(responsible__isnull=True)
    if request.GET.get('unrouted')=='1': qs=qs.filter(location__isnull=True)
    visible=cases_for(request.officer)
    locations=Location.objects.filter(pk__in=visible.values('location_id'))
    staff=Officer.objects.filter(pk__in=visible.values('responsible_id'))
    pager=Paginator(qs.order_by('-submitted_at'),20).get_page(request.GET.get('page'))
    params=request.GET.copy(); params.pop('page',None)
    return render(request,'service/applications.html',context(request,page=pager,tab=tab,archived=archived,statuses=Status.choices,categories=[x for x in Category.choices if x[0]!=Category.COORD],locations=locations,staff=staff,params=params.urlencode()))

@protected
@require_http_methods(['GET','POST'])
def detail(request,pk):
    app=get_object_or_404(cases_for(request.officer).select_related('location','responsible','consent__terms'),pk=pk)
    from .forms import VerificationForm
    verification_form=VerificationForm(request.POST if request.method=='POST' and request.POST.get('action')=='verify' else None,prefix='verify')
    is_assignment=request.method=='POST' and request.POST.get('action')=='assign'
    form=ProgressForm(request.POST if request.method=='POST' and not is_assignment else None,application=app,officer=request.officer)
    assignment_form=AssignmentForm(request.POST if is_assignment else None,prefix='assignment')
    if request.method=='POST':
        if request.POST.get('action')=='verify':
            if verification_form.is_valid():
                from .services import verify_application
                try:
                    verify_application(request.officer,app,verification_form.cleaned_data['decision']=='accept',verification_form.cleaned_data['note'],verification_form.cleaned_data['public_text'])
                    messages.success(request,'Verifikasi disimpan. Pemberitahuan diantrekan otomatis.')
                    return redirect('detail',pk=pk)
                except ValidationError as exc: verification_form.add_error(None,exc)
        elif is_assignment:
            if not has_role(request.officer,Role.SUPERADMIN): raise PermissionDenied()
            if assignment_form.is_valid():
                try:
                    assign_application(request.officer,app,**assignment_form.cleaned_data)
                    messages.success(request,'Penugasan disimpan.')
                    return redirect('detail',pk=pk)
                except ValidationError as exc: assignment_form.add_error(None,exc)
        elif form.is_valid():
            data=form.cleaned_data
            data['new_status']=data.pop('status')
            try:
                update_progress(request.officer,app,**data)
                messages.success(request,'Progres disimpan. Notifikasi masuk antrean.')
                return redirect('detail',pk=pk)
            except ValidationError as exc: form.add_error(None,exc)
    audit(f'officer:{request.officer.pk}','application.viewed',app.pk)
    return render(request,'service/detail.html',context(request,app=app,form=form,verification_form=verification_form,evidence=app.evidence.order_by('-submitted_at','-pk'),assignment_form=assignment_form,identity=[(label,app.identity.get(key,'')) for key,label in FIELDS],screenings=app.screenings.order_by('-version'),progress=app.progress.select_related('actor').all(),notes=app.notes.select_related('actor').all(),history=app.assignment_history.select_related('old_location','new_location','officer').order_by('-at'),notifications=app.notifications.order_by('-queued_at')[:30]))

@protected
@require_http_methods(['GET','POST'])
def management(request):
    if not has_role(request.officer,Role.SUPERADMIN): raise PermissionDenied()
    form=InvitationForm(request.POST or None)
    raw=None
    if request.method=='POST' and form.is_valid():
        try:
            raw,code=create_activation(**form.cleaned_data)
            audit(f'officer:{request.officer.pk}','activation.created',code.pk)
        except ValidationError as exc:
            form.add_error(None,exc)
    return render(request,'service/management.html',context(request,form=form,raw=raw,codes=ActivationCode.objects.select_related('location').order_by('-pk')[:20]))

@protected
@require_GET
def notifications(request):
    qs=Notification.objects.all() if has_role(request.officer,Role.SUPERADMIN) else Notification.objects.filter(application__in=cases_for(request.officer))
    return render(request,'service/notifications.html',context(request,notifications=qs.select_related('application').order_by('-queued_at')[:100],notification_mode=settings.NOTIFICATION_MODE))

@require_GET
def health(request):
    # DB-backed probe without exposing records or configuration.
    RuntimeCursor.objects.exists()
    return HttpResponse('ok',content_type='text/plain')


@protected
@require_http_methods(['GET','POST'])
def application_edit(request, pk=None):
    from django.db import transaction
    from .forms import IdentityForm
    from .services import edit_application, submit_registration, submit_screening
    app = get_object_or_404(cases_for(request.officer),pk=pk) if pk else None
    initial = dict(app.identity) if app else {}
    if app:
        latest = app.screenings.order_by('-version').first()
        initial.update(screening=latest.text if latest else '',expected_updated=app.updated_at.isoformat())
    form = IdentityForm(request.POST or None,initial=initial,creating=app is None)
    if request.method=='POST' and form.is_valid():
        try:
            with transaction.atomic():
                data=form.cleaned_data
                identity={key:data[key] for key,_ in FIELDS}
                if app:
                    app=edit_application(request.officer,app,identity,data['reason'],data['screening'],data['expected_updated'])
                else:
                    user=data['telegram']
                    from .services import active_application
                    if active_application(user):
                        raise ValidationError('Pemohon sudah memiliki permohonan aktif. Gunakan fitur edit.')
                    RegistrationDraft.objects.update_or_create(user=user,defaults={'data':identity,'step':9,'form_status':'DRAFT_REGISTRASI'})
                    app,_=submit_registration(user)
                    if data['screening'].strip():
                        app=submit_screening(user,app,data['screening'])
                    Progress.objects.create(application=app,old_status=app.status,new_status=app.status,actor=request.officer,reason=data['reason'])
                    audit(f'officer:{request.officer.pk}','application.created_by_staff',app.pk)
                messages.success(request,'Data pemohon disimpan. Perjalanan permohonan tetap mengikuti tahap yang berlaku.')
                return redirect('detail',pk=app.pk)
        except ValidationError as exc:
            form.add_error(None,exc)
    return render(request,'service/form.html',context(request,form=form,title='Edit data pemohon' if app else 'Tambah data pemohon',back_url='applications',multipart=False))


@protected
@require_http_methods(['GET','POST'])
def application_delete(request,pk):
    from .services import archive_application, require_coordinator
    require_coordinator(request.officer)
    app=get_object_or_404(cases_for(request.officer),pk=pk)
    error=''
    if request.method=='POST':
        try:
            archive_application(request.officer,app,request.POST.get('reason',''))
            messages.success(request,'Permohonan dihapus dari daftar aktif dan masuk arsip. Riwayat audit tetap tersimpan.')
            return redirect('applications')
        except ValidationError as exc:
            error=' '.join(exc.messages)
    return render(request,'service/delete.html',context(request,app=app,error=error))


@protected
@require_http_methods(['POST'])
def application_restore(request,pk):
    from .services import restore_application, require_coordinator
    require_coordinator(request.officer)
    app=get_object_or_404(cases_for(request.officer,include_deleted=True),pk=pk,deleted_at__isnull=False)
    restore_application(request.officer,app)
    messages.success(request,'Permohonan dipulihkan. Status penutupan tidak diubah.')
    return redirect('detail',pk=pk)


@protected
@require_GET
def evidence_image(request,pk):
    from io import BytesIO
    from django.http import FileResponse
    item=get_object_or_404(AssessmentEvidence,pk=pk,application__in=cases_for(request.officer))
    audit(f'officer:{request.officer.pk}','evidence.viewed',item.pk)
    response=FileResponse(BytesIO(bytes(item.image)),content_type=item.mime,filename=f'bukti-{item.pk}.jpg',as_attachment=False)
    response['X-Content-Type-Options']='nosniff'
    response['Content-Security-Policy']="default-src 'none'; sandbox"
    return response


@protected
@require_http_methods(['GET','POST'])
def evidence_upload(request,pk):
    from .forms import EvidenceUploadForm
    from .uploads import read_upload
    from .services import submit_evidence, begin_assessment
    from django.db import transaction
    app=get_object_or_404(cases_for(request.officer),pk=pk)
    form=EvidenceUploadForm(request.POST or None,request.FILES or None)
    if request.method=='POST' and form.is_valid():
        try:
            with transaction.atomic():
                if app.status==Status.WAIT_ASSESS or not app.assessment_url:
                    begin_assessment(app.applicant.user,app)
                    app.refresh_from_db()
                submit_evidence(None,app,read_upload(form.cleaned_data['screenshot']),submitted_by=request.officer)
            messages.success(request,'Bukti disimpan sebagai kiriman petugas; tetap memerlukan verifikasi.')
            return redirect('detail',pk=pk)
        except ValidationError as exc:
            form.add_error(None,exc)
    return render(request,'service/form.html',context(request,form=form,title='Unggah bukti Self Asesmen',back_url='applications',multipart=True))


@protected
@require_http_methods(['GET','POST'])
def branding(request):
    from .services import require_coordinator, site_config
    from .forms import BrandingForm
    from .uploads import clean_image, read_upload
    require_coordinator(request.officer)
    config=site_config()
    form=BrandingForm(request.POST or None,request.FILES or None,instance=config)
    if request.method=='POST' and form.is_valid():
        try:
            if form.cleaned_data['logo_upload']:
                data,mime,_=clean_image(read_upload(form.cleaned_data['logo_upload']))
                config.logo=data; config.logo_mime=mime
            elif form.cleaned_data['remove_logo']:
                config.logo=None; config.logo_mime=''
            form.save()
            audit(f'officer:{request.officer.pk}','branding.saved')
            messages.success(request,'Tampilan dashboard dan tautan Self Asesmen diperbarui.')
            return redirect('branding')
        except ValidationError as exc:
            form.add_error(None,exc)
    return render(request,'service/form.html',context(request,form=form,title='Tampilan dashboard & Self Asesmen',back_url='management',multipart=True))


@never_cache
@require_GET
def logo_image(request):
    from .services import site_config
    from django.http import Http404
    config=site_config()
    if not config.logo:
        raise Http404()
    response=HttpResponse(bytes(config.logo),content_type=config.logo_mime)
    response['X-Content-Type-Options']='nosniff'
    return response


@protected
@require_http_methods(['GET','POST'])
def accounts(request):
    from .services import require_coordinator, save_account
    from .forms import AccountCreateForm
    from django.db import transaction
    require_coordinator(request.officer)
    form=AccountCreateForm(request.POST or None)
    if request.method=='POST' and form.is_valid():
        try:
            with transaction.atomic():
                user=form.save()
                save_account(request.officer,form.cleaned_data,new_user=user)
            messages.success(request,'Akun dibuat. Tautkan Telegram melalui undangan aktivasi untuk menerima notifikasi.')
            return redirect('accounts')
        except ValidationError as exc:
            form.add_error(None,exc)
    qs=Officer.objects.select_related('web_user','telegram').order_by('pk')
    q=request.GET.get('q','').strip()
    if q:
        from django.db.models import Q
        qs=qs.filter(Q(web_user__username__icontains=q)|Q(web_user__first_name__icontains=q)|Q(role__icontains=q))
    return render(request,'service/accounts.html',context(request,form=form,accounts=qs))


@protected
@require_http_methods(['GET','POST'])
def account_edit(request,pk):
    from .services import require_coordinator, save_account
    from .forms import AccountEditForm
    from django.contrib.auth import update_session_auth_hash
    require_coordinator(request.officer)
    officer=get_object_or_404(Officer.objects.select_related('web_user'),pk=pk,web_user__isnull=False)
    web=officer.web_user
    initial={key:getattr(web,key) for key in ['username','first_name','last_name','email']}
    initial.update(role=officer.role,active=officer.verified and web.is_active,all_locations=officer.all_locations,locations=officer.assignments.filter(active=True).values_list('location_id',flat=True))
    form=AccountEditForm(request.POST or None,initial=initial,officer=officer)
    if request.method=='POST' and form.is_valid():
        try:
            saved=save_account(request.officer,form.cleaned_data,officer=officer)
            if saved.web_user_id==request.user.pk:
                update_session_auth_hash(request,saved.web_user)
            messages.success(request,'Akun dan kewenangan diperbarui.')
            return redirect('applications' if saved.web_user_id==request.user.pk and saved.role!=Role.SUPERADMIN else 'accounts')
        except ValidationError as exc:
            form.add_error(None,exc)
    return render(request,'service/form.html',context(request,form=form,title='Edit akun · '+web.username,back_url='accounts',multipart=False))


@protected
@require_GET
def live_events(request):
    from django.db.models import Max
    qs=cases_for(request.officer)
    latest=qs.aggregate(latest=Max('updated_at'))['latest']
    data={'total':qs.count(),'waiting':qs.filter(status=Status.WAIT_VERIFY).count(),'revision':latest.isoformat() if latest else '', 'notification_mode':settings.NOTIFICATION_MODE}
    if has_role(request.officer,Role.SUPERADMIN):
        data['notification_failed']=Notification.objects.filter(status='failed').count()
    from django.http import JsonResponse
    return JsonResponse(data)
