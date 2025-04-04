from django.urls import path
from .views import *

urlpatterns = [
    path('chat/', chatbot, name='chatbot'),
    path('dashboard/', dashboard, name='dashboard'),
    path('api/chatbot/', chatbot_api, name='chatbot_api'),  # API for chatbot
    path('display_prompts/', display_prompts, name='display_prompts'),  # API for chatbot
    path('update_prompt/', update_prompt, name='update_prompt'),  # API for chatbot,
    path("api/get_chat_history/", get_chat_history, name="get_chat_history"),  
    path("user_management/", user_management, name="user_management"),  
    path("add_users_roles/", add_users_roles, name="add_users_roles"), 
    path("user_login/", user_login, name="user_login"), 
    path('rooms/', room_data_list, name='room_data_list'),
    path('rooms/add/', add_room, name='add_room'),  # Add room view
    path('get_room_models/', get_room_models, name='get_room_models'),
    path('rooms/edit/', edit_room, name='edit_room'),
    path('delete-room/', delete_room, name='delete_room'),
    path('room-models/', room_model_list, name='room_model_list'),
    path('room-models/save/', save_room_model, name='save_room_model'),
    path('room-models/delete/', delete_room_model, name='delete_room_model'),
    path('installation-form/', installation_form, name='installation_form'),
    path('get-room-type/', get_room_type, name='get_room_type'),
    path('user_logout',user_logout,name='user_logout')
]
