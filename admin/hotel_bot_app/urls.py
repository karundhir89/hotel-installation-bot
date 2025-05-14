from django.urls import path
from .views import *

urlpatterns = [
    path('chat/', chatbot, name='chatbot'),
    path('home/', home, name='home'),
    path('api/chatbot/', chatbot_api, name='chatbot_api'),  # API for chatbot
    path('display_prompts/', display_prompts, name='edit_prompts'),  # Changed name to edit_prompts
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
    path('inventory/', inventory_list, name='inventory_list'),
    path('room-models/save/', save_room_model, name='save_room_model'),
    path('room-models/delete/', delete_room_model, name='delete_room_model'),
    path('installation-form/', installation_form, name='installation_form'),
    path('get-room-type/', get_room_type, name='get_room_type'),
    path('user_logout',user_logout,name='user_logout'),
    path('save_inventory/',save_inventory,name='save_inventory'),
    path('save_admin_installation/',save_admin_installation,name='save_admin_installation'),
    path('delete_inventory/',delete_inventory,name='delete_inventory'),
    path('delete_products_data/',delete_products_data,name='delete_products_data'),
    path('delete_installation/',delete_installation,name='delete_installation'),
    path('install/',install_list,name='install_list'),
    path('products/',product_data_list,name='product_data_list'),
    path('save_product_data/',save_product_data,name='save_product_data'),
    path('schedule/',schedule_list,name='schedule_list'),
    path('save_schedule/',save_schedule,name='save_schedule'),
    path('delete_schedule/',delete_schedule,name='delete_schedule'),
    path('inventory_shipment/', inventory_shipment, name='inventory_shipment'),
    path('get_product_item_num/', get_product_item_num, name='get_product_item_num'),
    path('inventory_received/', inventory_received, name='inventory_received'),
    path('inventory_received_item_num/', inventory_received_item_num, name='inventory_received_item_num'),
    path('inventory_pull/', inventory_pull, name='inventory_pull'),
    path('chat_history/', chat_history, name='chat_history'),
    path('chat_history/<int:session_id>/', view_chat_history, name='view_chat_history'),
    
    # New URLs for Product Room Model
    path('product-room-models/', product_room_model_list, name='product_room_model_list'),
    path('save_product_room_model/', save_product_room_model, name='save_product_room_model'),
    path('delete_product_room_model/', delete_product_room_model, name='delete_product_room_model'),
    path('get_floor_products/', get_floor_products, name='get_floor_products'),
    path('get_room_products/', get_room_products, name='get_room_products'),
    # New URLs for user-facing product lists with download
    path('floor-products/', floor_products_list, name='floor_products_list'),
    path('room-products/', room_number_products_list, name='room_number_products_list'),


    path('issue_list/', issue_list, name='issue_list'),
    path('issue_detail/<int:issue_id>/', issue_detail, name='issue_detail'),
    path('issue_create/', issue_create, name='issue_create'),
    path('issues/<int:issue_id>/comment/invited/', invited_user_comment_create, name='invited_user_comment_create'),
]
