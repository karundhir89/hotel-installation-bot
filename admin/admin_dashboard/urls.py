from django.urls import path
from . import views

urlpatterns = [
    path('',views.show_login,name='login_page'),
    path('account/login/', views.my_view, name='login'),
    path('logout',views.logout_view,name='logout')
]
