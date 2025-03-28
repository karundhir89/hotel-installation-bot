from django.urls import path
from . import views

urlpatterns = [
    path('',views.show_login,name='login_page'),
    path('account/login/', views.my_view, name='login'),
    path('dashboard',views.dashboard,name='dashboard'),
    path('logout',views.logout_view,name='logout'),
    path('permissions',views.get_permissions,name='get_permissions'),
    path('section-permissions',views.section_permissions,name='section-permissions')
]
