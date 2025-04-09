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
    path('inventory_list/', inventory_list, name='inventory_list'),
    path('room-models/save/', save_room_model, name='save_room_model'),
    path('room-models/delete/', delete_room_model, name='delete_room_model'),
    path('installation-form/', installation_form, name='installation_form'),
    path('get-room-type/', get_room_type, name='get_room_type'),
    path('user_logout',user_logout,name='user_logout'),
    path('save_inventory/',save_inventory,name='save_inventory'),
    path('save_installation/',save_installation,name='save_installation'),
    path('delete_inventory/',delete_inventory,name='delete_inventory'),
    path('delete_products_data/',delete_products_data,name='delete_products_data'),
    path('delete_installation/',delete_installation,name='delete_installation'),
    path('install_list/',install_list,name='install_list'),
    path('product_data_list/',product_data_list,name='product_data_list'),
    path('save_product_data/',save_product_data,name='save_product_data'),
    path('schedule_list/',schedule_list,name='schedule_list'),
    path('save_schedule/',save_schedule,name='save_schedule'),
    path('delete_schedule/',delete_schedule,name='delete_schedule'),
    path('inventory_shipment/', inventory_shipment, name='inventory_shipment'),
    path('get_product_item_num/', get_product_item_num, name='get_product_item_num'),
    path('inventory_received/', inventory_received, name='inventory_received'),
    path('inventory_received_item_num/', inventory_received_item_num, name='inventory_received_item_num'),
    path('inventory_pull/', inventory_pull, name='inventory_pull'),
    path('inventory_pull_item/', inventory_pull_item, name='inventory_pull_item'),
    path('installation_control_form/', installation_control_form, name='installation_control_form'),

    

    
    
    
    
    
    

    
]
