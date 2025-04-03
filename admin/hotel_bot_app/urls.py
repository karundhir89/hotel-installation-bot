from django.urls import path
from .views import *

urlpatterns = [
    path('chat/', chatbot, name='chatbot'),
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
]
