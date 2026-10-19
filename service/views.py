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
from .access import cases_for, has_role, assignments
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
    if not assignments(officer).exists(): raise PermissionDenied('Akun belum memiliki penugasan terverifikasi dan aktif.')
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
    return {'is_coordinator':has_role(request.officer,Role.COORD),'is_system':has_role(request.officer,Role.SYSTEM),'officer':request.officer,**values}

@protected
@require_GET
def overview(request):
    qs=cases_for(request.officer)
    counts=dict(qs.values_list('status').annotate(n=Count('pk')))
    cards=[{'label':'Registrasi terkirim','value':qs.count(),'code':''}]+[{'label':label,'value':counts.get(key,0),'code':key} for key,label in Status.choices]
    stale=qs.exclude(status__in=CLOSED).filter(updated_at__lt=timezone.now()-timedelta(days=settings.STALE_DAYS))
    return render(request,'service/overview.html',context(request,cards=cards,unassigned=qs.filter(responsible__isnull=True).count(),unrouted=qs.filter(location__isnull=True).count(),stale=stale.count(),stale_days=settings.STALE_DAYS,recent=qs.select_related('location','responsible').order_by('-updated_at')[:6],notification_mode=settings.NOTIFICATION_MODE))

@protected
@require_GET
def applications(request):
    qs=cases_for(request.officer).select_related('location','responsible')
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
    return render(request,'service/applications.html',context(request,page=pager,statuses=Status.choices,categories=[x for x in Category.choices if x[0]!=Category.COORD],locations=locations,staff=staff,params=params.urlencode()))

@protected
@require_http_methods(['GET','POST'])
def detail(request,pk):
    app=get_object_or_404(cases_for(request.officer).select_related('location','responsible','consent__terms'),pk=pk)
    is_assignment=request.method=='POST' and request.POST.get('action')=='assign'
    form=ProgressForm(request.POST if request.method=='POST' and not is_assignment else None,application=app,officer=request.officer)
    assignment_form=AssignmentForm(request.POST if is_assignment else None,prefix='assignment')
    if request.method=='POST':
        if is_assignment:
            if not has_role(request.officer,Role.COORD): raise PermissionDenied()
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
    return render(request,'service/detail.html',context(request,app=app,form=form,assignment_form=assignment_form,identity=[(label,app.identity.get(key,'')) for key,label in FIELDS],screenings=app.screenings.order_by('-version'),progress=app.progress.select_related('actor').all(),notes=app.notes.select_related('actor').all(),history=app.assignment_history.select_related('old_location','new_location','officer').order_by('-at'),notifications=app.notifications.order_by('-queued_at')[:30]))

@protected
@require_http_methods(['GET','POST'])
def management(request):
    if not has_role(request.officer,Role.SYSTEM): raise PermissionDenied()
    form=InvitationForm(request.POST or None)
    raw=None
    if request.method=='POST' and form.is_valid():
        raw,code=create_activation(**form.cleaned_data)
        audit(f'officer:{request.officer.pk}','activation.created',code.pk)
    return render(request,'service/management.html',context(request,form=form,raw=raw,codes=ActivationCode.objects.select_related('location').order_by('-pk')[:20]))

@protected
@require_GET
def notifications(request):
    qs=Notification.objects.all() if has_role(request.officer,Role.SYSTEM) else Notification.objects.filter(application__in=cases_for(request.officer))
    return render(request,'service/notifications.html',context(request,notifications=qs.select_related('application').order_by('-queued_at')[:100],notification_mode=settings.NOTIFICATION_MODE))

@require_GET
def health(request):
    # DB-backed probe without exposing records or configuration.
    RuntimeCursor.objects.exists()
    return HttpResponse('ok',content_type='text/plain')
