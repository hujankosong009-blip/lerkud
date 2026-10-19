from django.contrib import admin
from django.contrib.auth.views import LogoutView
from django.urls import path
from service import views
urlpatterns = [path('login/',views.ThrottledLoginView.as_view(),name='login'),path('logout/',LogoutView.as_view(),name='logout'),path('',views.overview,name='overview'),path('permohonan/',views.applications,name='applications'),path('permohonan/<uuid:pk>/',views.detail,name='detail'),path('pengelolaan/',views.management,name='management'),path('notifikasi/',views.notifications,name='notifications'),path('health/',views.health),path('kelola/',admin.site.urls)]
