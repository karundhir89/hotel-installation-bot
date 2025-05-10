import ast
import json
import random
import string
from datetime import date, datetime
from functools import wraps
from django.db.models.functions import Lower
from django.urls import reverse
import bcrypt
import environ
import requests
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.mail import send_mail
from django.http import JsonResponse, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.utils.timezone import now
from django.views.decorators.csrf import csrf_exempt
from hotel_bot_app.utils.helper import (fetch_data_from_sql,
                                         format_gpt_prompt,
                                         generate_final_response,
                                         gpt_call_json_func,gpt_call_json_func_two,
                                         load_database_schema,
                                         verify_sql_query,
                                         generate_sql_prompt,
                                         generate_natural_response_prompt,
                                         output_praser_gpt,
                                         intent_detection_prompt)
from openai import OpenAI
from html import escape
import xlwt

from django.db.models import Q
from django.contrib.auth import get_user_model # Use this if settings.AUTH_USER_MODEL is Django's default
from django.contrib.auth.decorators import login_required, user_passes_test # For permission checking
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger # Import Paginator

from .models import *
from .models import ChatSession
from django.utils.timezone import localtime
from django.db import connection
from .forms import IssueForm, CommentForm, IssueUpdateForm # Import the forms
import logging

logger = logging.getLogger(__name__)

env = environ.Env()
environ.Env.read_env()

password_generated = "".join(random.choices(string.ascii_letters + string.digits, k=6))
open_ai_key = env("open_ai_api_key")

client = OpenAI(api_key=open_ai_key)

User = InvitedUser # Or User = get_user_model()

def session_login_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.session.get("user_id"):
            return redirect("user_login")
        return view_func(request, *args, **kwargs)

    return wrapper


def extract_values(json_obj, keys):
    """
    Extract values from a JSON object based on the provided list of keys.
    :param json_obj: Dictionary (parsed JSON object)
    :param keys: List of keys to extract values for
    :return: None (prints formatted output)
    """
    table_selected = ""
    for key in keys:
        value = json_obj.get(key, None)
        table_selected += f"Table name is '{key}' and column name is {value}\n\n"
    print("table selected ,,,,,,", table_selected)
    return table_selected


def get_chat_history_from_db(session_id):

    if not session_id:
        return JsonResponse({"chat_history": []})  # No session, return empty history

    session = get_object_or_404(ChatSession, id=session_id)
    history_messages = list(
        ChatHistory.objects.filter(session=session).values("role", "message")
    )
    converted_messages = [
    {'role': msg['role'], 'content': msg['message']}
    for msg in history_messages
    ]
    return converted_messages


@csrf_exempt
def chatbot_api(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            user_message = data.get("message", "").strip()
        except json.JSONDecodeError:
            return JsonResponse({"response": "⚠️ Invalid request format."}, status=400)

        if not user_message:
            return JsonResponse({"response": "⚠️ Please enter a message."}, status=400)

        # --- Session Management ---
        session_id = request.session.get("chat_session_id")
        session = None
        print('session id',session_id)
        if session_id:
            try:
                session = ChatSession.objects.get(id=session_id)
            except ChatSession.DoesNotExist:
                session_id = None # Force creation of a new session

        if not session_id:
            session = ChatSession.objects.create()
            request.session["chat_session_id"] = session.id
            request.session.set_expiry(3600 * 8) # 8 hours
            print(f"Created new chat session: {session.id}")
        else:
             print(f"Using existing chat session: {session_id}")


        # --- Log User Message ---
        try:
            ChatHistory.objects.create(session=session, message=user_message, role="user")
        except Exception as e:
            print(f"Error saving user message to chat history: {e}")
            # Non-critical, proceed with generation but log the issue


        # --- New Core Chatbot Logic (Two-Stage LLM) ---
        bot_message = "Sorry, I encountered an unexpected issue and couldn't process your request. Please try again later." # Default error
        final_sql_query = None # Store the query that was actually executed
        rows = None # Store the results

        try:
            # 1. Load Schema
            try:
                DB_SCHEMA = load_database_schema()
            except Exception as e:
                print(f"Critical Error loading database schema: {e}")
                raise Exception("Failed to load schema information.")

            # 2. First LLM Call: Intent Recognition & Conditional SQL Generation
            intent_response = None
            try:
                intent_prompt = intent_detection_prompt(user_message)

                intent_prompt_first_output = json.loads(gpt_call_json_func_two(
                    intent_prompt,
                    gpt_model="gpt-4o",
                    openai_key=open_ai_key,
                    json_required=True
                ))
                print('intent_prompt_first_output',intent_prompt_first_output)
                

                intent_prompt_system_prompt,intent_prompt_user_prompt = generate_sql_prompt(user_message, DB_SCHEMA)
                if 'response' not in intent_prompt_first_output:
                    print("Its a db query, as identify by intent_detection_prompt.")
                    intent_prompt_system_prompt={"role":"system","content":intent_prompt_system_prompt + f'## Relevant Context : ##{intent_prompt_first_output}'}
                else:
                    print("we got response")
                    intent_prompt_system_prompt={"role":"system","content":intent_prompt_system_prompt}

                intent_prompt_user_prompt={"role":"user","content":intent_prompt_user_prompt}
                print(1)
                if session_id!=None:
                    chat_history_memory=get_chat_history_from_db(session_id)
                    print(2)
                    
                    if len(chat_history_memory) > 5:
                        chat_history_memory = chat_history_memory[-5:]
                    
                    chat_history_memory=[intent_prompt_system_prompt]+chat_history_memory
                    
                    # print('chat_history_memory ...........',chat_history_memory)
                    sql_response = json.loads(gpt_call_json_func_two(
                        chat_history_memory,
                        gpt_model="gpt-4o",
                        openai_key=open_ai_key,
                        json_required=True
                    ))
                    print('sql_response ',sql_response)
                if session_id==None:
                    # print("session id is none",[{"role":"system","content":intent_prompt_system_prompt},{"role":"user","content":user_message}])
                    sql_response = json.loads(gpt_call_json_func_two(
                        [intent_prompt_system_prompt,{"role":"user","content":user_message}],
                        gpt_model="gpt-4o",
                        openai_key=open_ai_key,
                        json_required=True
                    ))
            except Exception as e:
                print(f"Error during Intent/SQL Generation LLM call: {e}")
                # Fall through, sql_response remains None

            if not sql_response or not isinstance(sql_response, dict):
                print("Error: Failed to get valid JSON response from Intent/SQL LLM.")
                raise Exception("Failed to understand request intent.")

            needs_sql = sql_response.get("needs_sql")
            initial_sql_query = sql_response.get("query")
            direct_answer = sql_response.get("direct_answer")

            # 3. Handle based on Intent
            if needs_sql is False and direct_answer:
                print("Intent LLM provided a direct answer.")
                bot_message = direct_answer
                # Skip SQL execution and proceed directly to logging/returning the direct answer

            elif needs_sql is True and initial_sql_query:
                print(f"\n\nGenerated query: \n\n{initial_sql_query}\n\n\n")
                final_sql_query = initial_sql_query # Tentatively set the final query

                # 4. Execute SQL (and verify/retry if needed)
                try:
                    # Initial attempt
                    rows = fetch_data_from_sql(initial_sql_query)
                    print(f"Initial query execution successful.",rows)

                except Exception as db_error:
                    print(f"Initial DB execution error: {db_error}. Attempting verification.")

                    verification = None
                    try:
                        verification = verify_sql_query(
                            user_message=user_message,
                            sql_query=initial_sql_query, # Verify the original query
                            prompt_data=DB_SCHEMA,
                            error_message=str(db_error),
                            gpt_model="gpt-4o"
                        )
                    except Exception as verify_e:
                        print(f"Error during SQL verification call: {verify_e}")

                    print(f"Verification result: {verification}")

                    if verification and isinstance(verification, dict) and not verification.get("is_valid") and verification.get("recommendation"):
                        recommended_query = verification["recommendation"]
                        print(f"Verification recommended new query: {recommended_query}")
                        try:
                            rows = fetch_data_from_sql(recommended_query)
                            final_sql_query = recommended_query # Update the final query executed
                            print("Retry with recommended query successful.",rows)
                        except Exception as second_error:
                            print(f"Retry with recommended query failed: {second_error}")
                            # Clear rows and final_sql_query as the attempt failed
                            rows = None
                            final_sql_query = initial_sql_query # Revert to indicate initial attempt failed
                            # Don't raise here, let the final response generation handle the failure state
                    else:
                        print("SQL Verification did not provide a usable correction or retry failed.")
                        # Clear rows as the query failed
                        rows = None
                        # Keep final_sql_query as the one that failed for context

                # 5. Second LLM Call: Generate Natural Language Response (if SQL was attempted)
                # This block runs whether SQL succeeded, failed, or returned no rows
                try:
                    response_prompt = generate_natural_response_prompt(user_message, final_sql_query, rows)
                    # print('response prompt is :::::::',response_prompt)
                    bot_message = output_praser_gpt( # Use output_praser_gpt as we expect text
                        response_prompt,
                        gpt_model="gpt-4o",
                        json_required=False,
                        temperature=0.7 # Allow slightly more creativity for natural language
                    )
                    if not bot_message or not isinstance(bot_message, str):
                         print(f"Error: Natural response generation returned invalid data: {bot_message}")
                         raise Exception("Failed to format the final natural response.")
                except Exception as e:
                    print(f"Error during Natural Response Generation LLM call: {e}")
                    raise Exception("Failed to generate the final natural response.")

            else:
                # Invalid state from first LLM call (e.g., needs_sql=true but no query)
                print(f"Error: Invalid state from Intent LLM. Response: {intent_response}")
                raise Exception("Received an inconsistent response from the intent analysis.")

        except Exception as e:
            print(f"Error in chatbot_api main logic: {e}")
            # Use the default error message
            # bot_message = "Sorry, I encountered an unexpected issue..."
            internal_error_message = f"Failed processing user message '{user_message}'. Error: {str(e)}"
            print(internal_error_message)
            # Ensure the default message is used if an exception occurred before natural response generation
            if bot_message == "Sorry, I encountered an unexpected issue and couldn't process your request. Please try again later.":
                 # If the default message is still set, it means we didn't reach the natural response stage or it failed.
                 pass # Keep the default message
            elif not bot_message or not isinstance(bot_message, str):
                 # If bot_message got corrupted somehow during error handling
                 bot_message = "Sorry, I encountered an unexpected issue and couldn't process your request. Please try again later."

        
        messages=bot_message
        try:
            ChatHistory.objects.create(session=session, message=messages, role="assistant")
        except Exception as e:
             print(f"Error saving assistant message to chat history: {e}")
             # Non-critical


        # --- Return Response ---
        return JsonResponse({"response": bot_message,"table_info":rows})

    # --- Handle Non-POST Requests ---
    return JsonResponse({"error": "Invalid request method. Only POST is allowed."}, status=405)

def convert_to_html_table(data):
    html = ['<table>']

    # Header
    html.append('<tr>')
    for col in data['columns']:
        html.append(f'<th>{escape(col)}</th>')
    html.append('</tr>')

    # Rows
    for row in data['rows']:
        html.append('<tr>')
        for cell in row:
            if isinstance(cell, datetime):
                cell = cell.isoformat()
            html.append(f'<td>{escape(str(cell))}</td>')
        html.append('</tr>')

    html.append('</table>')
    return '\n'.join(html)

@csrf_exempt
def get_chat_history(request):
    session_id = request.session.get("chat_session_id")

    if not session_id:
        return JsonResponse({"chat_history": []})  # No session, return empty history

    session = get_object_or_404(ChatSession, id=session_id)
    history_messages = list(
        ChatHistory.objects.filter(session=session).values("role", "message")
    )
    return JsonResponse({"chat_history": history_messages})


def chatbot(request):
    return render(request, "chatbot.html")

@login_required
def display_prompts(request):
    print(request)
    prompts = Prompt.objects.all()  # Fetch all records
    for prompt in prompts:
        print(prompt.id, prompt.prompt_number, prompt.description)
    return render(request, "edit_prompt.html", {"prompts": prompts})

@login_required
def update_prompt(request):
    if request.method == "POST":
        prompt_id = request.POST.get("prompt_id")  # Get the ID
        prompt_description = request.POST.get(
            "prompt_description"
        )  # Get the new description

        try:
            prompt = Prompt.objects.get(id=prompt_id)  # Fetch the object
            prompt.description = prompt_description  # Update the description
            prompt.save()  # Save changes
            print("Updated successfully")
        except Prompt.DoesNotExist:
            print("Prompt not found")

    return render(request, "edit_prompt.html")

@login_required
def user_management(request):
    prompts = InvitedUser.objects.all()
    print("users", prompts)

    return render(request, "user_management.html", {"prompts": prompts})

@login_required
def add_users_roles(request):
    print(request.POST)
    if request.method == "POST":
        name = request.POST.get("name")  # Get the ID
        email = request.POST.get("email")  # Get the new description
        roles = request.POST.get("role")  # Get the new description
        status = request.POST.get("status")  # Get the new description
        password = request.POST.get("password")  # Get the password
        roles_list = roles.split(", ") if roles else []
        print(name, email, type(roles_list), roles_list, status, password)

        user = InvitedUser.objects.create(
            name=name,
            role=roles_list,
            last_login=now(),
            email=email,
            password=bcrypt.hashpw(password.encode(), bcrypt.gensalt()),
        )

    return render(request, "add_users_roles.html")

@csrf_exempt
def user_login(request):
    # Redirect to home page if already logged in
    if request.session.get("user_id"):
        return redirect("/home")

    if request.method == "POST":
        try:
            data = json.loads(request.body)
            username = data.get("email")
            entry_password = data.get("password")

            if not username or not entry_password:
                return JsonResponse(
                    {"error": "Username and password are required."}, status=400
                )

            user = InvitedUser.objects.filter(email=username).first()

            if user is None:
                return JsonResponse({"error": "Email does not exist."}, status=404)

            stored_hashed_password = bytes(user.password)  # convert memoryview to bytes
            if bcrypt.checkpw(entry_password.encode(), stored_hashed_password):
                request.session["user_id"] = user.id
                request.session["user_email"] = user.email
                return JsonResponse({"message": "successful."}, status=200)

            return JsonResponse({"error": "Incorrect password."}, status=401)

        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON data."}, status=400)
        except Exception as e:
            return JsonResponse({"error": f"An error occurred: {str(e)}"}, status=500)

    return render(request, "user_login.html")


@login_required
def room_data_list(request):
    # Fetch room data from the database, including related RoomModel
    rooms = RoomData.objects.select_related('room_model_id').all()

    # Pass the room data to the template
    return render(request, "room_data_list.html", {"rooms": rooms})


@login_required
def inventory_list(request):
    # Fetch room data from the database
    inventory = Inventory.objects.all()
    # Pass the room data to the template
    return render(request, "inventory.html", {"inventory": inventory})


@login_required
def get_room_models(request):
    room_models = RoomModel.objects.all()
    room_model_list = [
        {"id": model.id, "name": model.room_model} for model in room_models
    ]
    return JsonResponse({"room_models": room_model_list})


@login_required
def add_room(request):
    if request.method == "POST":
        room_number = request.POST.get("room")
        floor = request.POST.get("floor")
        king = request.POST.get("king")
        double = request.POST.get("double")
        exec_king = request.POST.get("exec_king")
        bath_screen = request.POST.get("bath_screen")
        left_desk = request.POST.get("left_desk")
        right_desk = request.POST.get("right_desk")
        to_be_renovated = request.POST.get("to_be_renovated")
        room_model_id = request.POST.get("room_model")
        description = request.POST.get("description")

        # Assuming room_model is a ForeignKey
        room_model = RoomModel.objects.get(id=room_model_id)
        # Check if room number already exists
        if RoomData.objects.filter(room=room_number).exists():
            return JsonResponse({"error": "Room number already exists!"}, status=400)

        try:
            RoomData.objects.create(
                room=room_number,
                floor=floor,
                king=king,
                double=double,
                exec_king=exec_king,
                bath_screen=bath_screen,
                left_desk=left_desk,
                right_desk=right_desk,
                to_be_renovated=to_be_renovated,
                room_model=room_model.room_model,
                room_model_id=room_model,
                description=description,
            )
            print("RoomData id", RoomData.id)
            return JsonResponse({"success": "Room added successfully"})
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=400)


@login_required
def edit_room(request):
    if request.method == "POST":
        try:
            room_id = request.POST.get("room_id")
            room = get_object_or_404(RoomData, id=room_id)

            # Don't update room number
            room.floor = request.POST.get("floor")
            room.king = request.POST.get("king")
            room.double = request.POST.get("double")
            room.exec_king = request.POST.get("exec_king")
            room.bath_screen = request.POST.get("bath_screen")
            room.description = request.POST.get("description")
            room.left_desk = request.POST.get("left_desk")
            room.right_desk = request.POST.get("right_desk")
            room.to_be_renovated = request.POST.get("to_be_renovated")

            # Update Room Model if given
            room_model_id = request.POST.get("room_model")
            if room_model_id:
                room_model = get_object_or_404(RoomModel, id=room_model_id)
                room.room_model = room_model.room_model
                room.room_model_id = room_model
                print("room = ", room_model)

            room.save()

            return JsonResponse({"success": "Room updated successfully!"})

        except RoomModel.DoesNotExist:
            return JsonResponse({"error": "Invalid room model!"}, status=400)
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=400)

    return JsonResponse({"error": "Invalid request"}, status=400)


@login_required
def delete_room(request):
    if request.method == "POST":
        room_id = request.POST.get("room_id")
        room = get_object_or_404(RoomData, id=room_id)

        try:
            room.delete()
            return JsonResponse({"success": "Room deleted successfully!"})
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=400)

    return JsonResponse({"error": "Invalid request"}, status=400)

@login_required
def room_model_list(request):
    room_models = RoomModel.objects.all()
    return render(request, "room_model_list.html", {"room_models": room_models})


@login_required
def install_list(request):
    # Get all installation records, including related user data
    install = Installation.objects.select_related(
        'prework_checked_by',
        'post_work_checked_by',
        'product_arrived_at_floor_checked_by',
        'retouching_checked_by'
    ).all()
    
    # Convert the dates to a proper format for use in the template
    for installation in install:
        if installation.day_install_began:
            installation.formatted_day_install_began = installation.day_install_began.strftime('%Y-%m-%d')
            installation.day_install_began = installation.day_install_began.strftime('%m-%d-%Y')
        if installation.day_install_complete:
            installation.formatted_day_install_complete = installation.day_install_complete.strftime('%Y-%m-%d')
            installation.day_install_complete = installation.day_install_complete.strftime('%m-%d-%Y')
    
    # Pass the modified install data to the template
    return render(request, "install.html", {"install": install})


@login_required
def product_data_list(request):
    product_data_list = ProductData.objects.all()
    return render(
        request, "product_data_list.html", {"product_data_list": product_data_list}
    )


@login_required
def schedule_list(request):
    schedule = Schedule.objects.all()
    # Convert the dates to a proper format for use in the template
    for one_schedule in schedule:
        if one_schedule.production_starts:
            one_schedule.formatted_production_starts = one_schedule.production_starts.strftime('%Y-%m-%d')
            one_schedule.production_starts = one_schedule.production_starts.strftime('%m-%d-%Y')
            
        if one_schedule.production_ends:
            one_schedule.formatted_production_ends = one_schedule.production_ends.strftime('%Y-%m-%d')
            one_schedule.production_ends = one_schedule.production_ends.strftime('%m-%d-%Y')
            
        if one_schedule.shipping_arrival:
            one_schedule.formatted_shipping_arrival = one_schedule.shipping_arrival.strftime('%Y-%m-%d')
            one_schedule.shipping_arrival = one_schedule.shipping_arrival.strftime('%m-%d-%Y')

        if one_schedule.shipping_depature:
            one_schedule.formatted_shipping_depature = one_schedule.shipping_depature.strftime('%Y-%m-%d')
            one_schedule.shipping_depature = one_schedule.shipping_depature.strftime('%m-%d-%Y')

        if one_schedule.custom_clearing_starts:
            one_schedule.formatted_custom_clearing_starts = one_schedule.custom_clearing_starts.strftime('%Y-%m-%d')
            one_schedule.custom_clearing_starts = one_schedule.custom_clearing_starts.strftime('%m-%d-%Y')

        if one_schedule.custom_clearing_ends:
            one_schedule.formatted_custom_clearing_ends = one_schedule.custom_clearing_ends.strftime('%Y-%m-%d')
            one_schedule.custom_clearing_ends = one_schedule.custom_clearing_ends.strftime('%m-%d-%Y')

        if one_schedule.arrive_on_site:
            one_schedule.formatted_arrive_on_site = one_schedule.arrive_on_site.strftime('%Y-%m-%d')
            one_schedule.arrive_on_site = one_schedule.arrive_on_site.strftime('%m-%d-%Y')

        if one_schedule.pre_work_starts:
            one_schedule.formatted_pre_work_starts = one_schedule.pre_work_starts.strftime('%Y-%m-%d')
            one_schedule.pre_work_starts = one_schedule.pre_work_starts.strftime('%m-%d-%Y')

        if one_schedule.pre_work_ends:
            one_schedule.formatted_pre_work_ends = one_schedule.pre_work_ends.strftime('%Y-%m-%d')
            one_schedule.pre_work_ends = one_schedule.pre_work_ends.strftime('%m-%d-%Y')

        if one_schedule.post_work_starts:
            one_schedule.formatted_post_work_starts = one_schedule.post_work_starts.strftime('%Y-%m-%d')
            one_schedule.post_work_starts = one_schedule.post_work_starts.strftime('%m-%d-%Y')

        if one_schedule.post_work_ends:
            one_schedule.formatted_post_work_ends = one_schedule.post_work_ends.strftime('%Y-%m-%d')
            one_schedule.post_work_ends = one_schedule.post_work_ends.strftime('%m-%d-%Y')

        if one_schedule.install_starts:
            one_schedule.formatted_install_starts = one_schedule.install_starts.strftime('%Y-%m-%d')
            one_schedule.install_starts = one_schedule.install_starts.strftime('%m-%d-%Y')

        if one_schedule.install_ends:
            one_schedule.formatted_install_ends = one_schedule.install_ends.strftime('%Y-%m-%d')
            one_schedule.install_ends = one_schedule.install_ends.strftime('%m-%d-%Y')

        if one_schedule.floor_opens:
            one_schedule.formatted_floor_opens = one_schedule.floor_opens.strftime('%Y-%m-%d')
            one_schedule.floor_opens = one_schedule.floor_opens.strftime('%m-%d-%Y')

        if one_schedule.floor_closes:
            one_schedule.formatted_floor_closes = one_schedule.floor_closes.strftime('%Y-%m-%d')
            one_schedule.floor_closes = one_schedule.floor_closes.strftime('%m-%d-%Y')

        if one_schedule.floor_completed:
            one_schedule.formatted_floor_completed = one_schedule.floor_completed.strftime('%Y-%m-%d')
            one_schedule.floor_completed = one_schedule.floor_completed.strftime('%m-%d-%Y')

    return render(request, "schedule.html", {"schedule": schedule})


@login_required
def save_room_model(request):
    print("ssssss")
    if request.method == "POST":
        model_id = request.POST.get("model_id")
        name = request.POST.get("name").strip()

        if not name:
            return JsonResponse({"error": "Model name is required"}, status=400)

        # Check for duplicate name (case-insensitive)
        existing_model = RoomModel.objects.filter(room_model__iexact=name)
        if model_id:
            existing_model = existing_model.exclude(id=model_id)

        if existing_model.exists():
            return JsonResponse(
                {"error": "A room model with this name already exists."}, status=400
            )

        if model_id:
            try:
                model = RoomModel.objects.get(id=model_id)
                model.room_model = name
                model.save()
                return JsonResponse({"success": "Room model updated successfully"})
            except RoomModel.DoesNotExist:
                return JsonResponse({"error": "Room model not found"}, status=404)
        else:
            RoomModel.objects.create(room_model=name)
            return JsonResponse({"success": "Room model created successfully"})

    return JsonResponse({"error": "Invalid request"}, status=400)


@login_required
def save_inventory(request):
    if request.method == "POST":
        inventory_id = request.POST.get("inventory_id")
        print(inventory_id, "ssssss  ")
        item = request.POST.get("item", "").strip()
        client_id = request.POST.get("client_id", "").strip()
        qty_ordered = request.POST.get("qty_ordered") or 0
        qty_received = request.POST.get("qty_received") or 0
        quantity_installed = request.POST.get("quantity_installed") or 0
        quantity_available = request.POST.get("quantity_available") or 0

        if not item:
            return JsonResponse({"error": "Item name is required"}, status=400)

        # Convert to appropriate data types
        try:
            qty_ordered = int(qty_ordered)
            qty_received = int(qty_received)
            quantity_installed = int(quantity_installed)
            quantity_available = int(quantity_available)
        except ValueError:
            return JsonResponse({"error": "Quantities must be integers"}, status=400)

        # Check for duplicates
        existing = Inventory.objects.filter(item__iexact=item, client_id=client_id)
        if inventory_id:
            existing = existing.exclude(id=inventory_id)

        if existing.exists():
            return JsonResponse(
                {"error": "This item already exists for the given client."}, status=400
            )

        if inventory_id:
            try:
                inventory = Inventory.objects.get(id=inventory_id)
                inventory.item = item
                inventory.client_id = client_id
                inventory.qty_ordered = qty_ordered
                inventory.qty_received = qty_received
                inventory.quantity_installed = quantity_installed
                inventory.quantity_available = quantity_available
                inventory.save()
                return JsonResponse({"success": True})
            except Inventory.DoesNotExist:
                return JsonResponse({"error": "Inventory item not found"}, status=404)
        else:
            Inventory.objects.create(
                item=item,
                client_id=client_id,
                qty_ordered=qty_ordered,
                qty_received=qty_received,
                quantity_installed=quantity_installed,
                quantity_available=quantity_available,
            )
            return JsonResponse({"success": True})

    return JsonResponse({"error": "Invalid request"}, status=400)


@login_required
def delete_room_model(request):
    if request.method == "POST":
        model_id = request.POST.get("model_id")
        try:
            room_model = RoomModel.objects.get(id=model_id)
            room_model.delete()
            return JsonResponse({"success": "Room Model deleted."})
        except RoomModel.DoesNotExist:
            return JsonResponse({"error": "Room Model not found."})
    return JsonResponse({"error": "Invalid request."})


@login_required
def delete_inventory(request):
    if request.method == "POST":
        model_id = request.POST.get("model_id")
        try:
            room_model = Inventory.objects.get(id=model_id)
            room_model.delete()
            return JsonResponse({"success": "Room Model deleted."})
        except Inventory.DoesNotExist:
            return JsonResponse({"error": "Room Model not found."})
    return JsonResponse({"error": "Invalid request."})


@login_required
def delete_schedule(request):
    if request.method == "POST":
        model_id = request.POST.get("model_id")
        try:
            schedule = Schedule.objects.get(id=model_id)
            schedule.delete()
            return JsonResponse({"success": "Room Model deleted."})
        except Inventory.DoesNotExist:
            return JsonResponse({"error": "Room Model not found."})
    return JsonResponse({"error": "Invalid request."})


@login_required
def delete_products_data(request):
    if request.method == "POST":
        model_id = request.POST.get("model_id")
        try:
            room_model = ProductData.objects.get(id=model_id)
            room_model.delete()
            return JsonResponse({"success": "Room Model deleted."})
        except ProductData.DoesNotExist:
            return JsonResponse({"error": "Room Model not found."})
    return JsonResponse({"error": "Invalid request."})

@session_login_required
def get_room_type(request):
    room_number = request.GET.get("room_number")

    try:
        room_data = RoomData.objects.get(room=room_number)
        room_type = room_data.room_model or ""
        room_model = RoomModel.objects.get(room_model=room_type)
        room_model_id = room_model.id
        product_room_models = ProductRoomModel.objects.filter(
            room_model_id=room_model_id
        )
        # Get Installation model for the room
        installation_data = Installation.objects.filter(room=room_number).first()
        saved_items = []
        check_items = []

        # Check if InstallDetail already exists
        existing_installs = InstallDetail.objects.filter(
            room_id=room_data
        ).select_related("product_id", "room_id", "room_model_id", "installed_by")
        print("existing_installs ::::::",existing_installs)

        if existing_installs.exists():
            for inst in existing_installs:
                try:
                    prm = ProductRoomModel.objects.get(product_id=inst.product_id, room_model_id=inst.room_model_id)
                    prm_id = prm.id
                except ProductRoomModel.DoesNotExist:
                    prm_id = None

                saved_items.append({
                    "install_id": inst.install_id,
                    "product_id": inst.product_id.id if inst.product_id else None,
                    "product_name": inst.product_name,
                    "room_id": inst.room_id.id if inst.room_id else None,
                    "room_model_id": inst.room_model_id.id if inst.room_model_id else None,
                    "product_room_model_id": prm_id,
                    "installed_by": inst.installed_by.name if inst.installed_by else None,
                    "installed_on": inst.installed_on.isoformat() if inst.installed_on else None,
                    "status": inst.status,
                    "product_client_id": inst.product_id.client_id if inst.product_id else None,
                })
                try:
                    # Add to check_items with install_id as ID
                    check_items.append({
                        "id": inst.install_id,
                        "label": f"({inst.product_id.client_id}) - {inst.product_name} ",
                        "type": "detail",
                    })
                except:
                    print(inst.product_id)
                    check_items.append({
                        "id": inst.install_id,
                        "label": f"({inst.product_name} ",
                        "type": "detail",
                    })
                    

        else:
            # Only create InstallDetails if none exist yet
            install_details_to_create = []
            for prm in product_room_models:
                install = InstallDetail(
                    installation=installation_data,
                    product_id=prm.product_id,
                    room_id=room_data,
                    room_model_id=room_model,
                    product_name=prm.product_id.description
                )
                install_details_to_create.append(install)

            # Bulk create for efficiency
            InstallDetail.objects.bulk_create(install_details_to_create)

            # Re-fetch created records with IDs
            created_installs = InstallDetail.objects.filter(
                installation=installation_data, room_id=room_data
            ).select_related("product_id")

            for inst in created_installs:
                try:
                    prm = ProductRoomModel.objects.get(product_id=inst.product_id, room_model_id=inst.room_model_id)
                    prm_id = prm.id
                except ProductRoomModel.DoesNotExist:
                    prm_id = None

                saved_items.append({
                    "install_id": inst.install_id,
                    "product_id": inst.product_id.id if inst.product_id else None,
                    "product_name": inst.product_name,
                    "room_id": inst.room_id.id if inst.room_id else None,
                    "room_model_id": inst.room_model_id.id if inst.room_model_id else None,
                    "product_room_model_id": prm_id,
                    "installed_by": inst.installed_by.name if inst.installed_by else None,
                    "installed_on": inst.installed_on.isoformat() if inst.installed_on else None,
                    "status": inst.status,
                    "product_client_id": inst.product_id.client_id if inst.product_id else None,
                })
                try:
                    check_items.append({
                        "id": inst.install_id,
                        "label": f"({inst.product_id.client_id}) -{inst.product_name}",
                        "type": "detail",
                    })

                except:
                    print(inst.product_id)
                    check_items.append({
                        "id": inst.install_id,
                        "label": f"({inst.product_name} ",
                        "type": "detail",
                    })

        # Process static Installation step items (IDs 0, 1, 12, 13)
        if installation_data:
            check_items.extend([
                {
                    "id": 0,
                    "label": "Pre-Work completed.",
                    "checked_by": installation_data.prework_checked_by.name if installation_data.prework_checked_by else None,
                    "check_on": localtime(installation_data.prework_check_on).isoformat() if installation_data.prework_check_on else None,
                    "status": installation_data.prework,
                    "type": "installation"
                },
                {
                    "id": 1,
                    "label": "The product arrived at the floor.",
                    "checked_by": installation_data.product_arrived_at_floor_checked_by.name if installation_data.product_arrived_at_floor_checked_by else None,
                    "check_on": localtime(installation_data.product_arrived_at_floor_check_on).isoformat() if installation_data.product_arrived_at_floor_check_on else None,
                    "status": installation_data.product_arrived_at_floor,
                    "type": "installation"
                },
                {
                    "id": 12,
                    "label": "Retouching.",
                    "checked_by": installation_data.retouching_checked_by.name if installation_data.retouching_checked_by else None,
                    "check_on": localtime(installation_data.retouching_check_on).isoformat() if installation_data.retouching_check_on else None,
                    "status": installation_data.retouching,
                    "type": "installation"
                },
                {
                    "id": 13,
                    "label": "Post Work.",
                    "checked_by": installation_data.post_work_checked_by.name if installation_data.post_work_checked_by else None,
                    "check_on": localtime(installation_data.post_work_check_on).isoformat() if installation_data.post_work_check_on else None,
                    "status": installation_data.post_work,
                    "type": "installation"
                },
            ])

        # Sort check_items by placing 0 and 1 at the beginning, and 12 and 13 at the end, while sorting the rest by ID
        check_items = sorted(
            check_items,
            key=lambda x: (
                x["id"] not in [0, 1],  # Ensure IDs 0 and 1 are first
                x["id"] in [12, 13],  # Ensure IDs 12 and 13 are last
                x["id"]  # Sort the rest of the IDs normally
            )
        )

        return JsonResponse(
            {
                "success": True,
                "room_type": room_type,
                "check_items": check_items,
                "saved_items": saved_items,
            }
        )

    except RoomData.DoesNotExist:
        return JsonResponse({"success": False, "message": "Room not found"})
    except RoomModel.DoesNotExist:
        return JsonResponse({"success": False, "message": "Room model not found"})

@session_login_required
def inventory_shipment(request):
    user_id = request.session.get("user_id")
    user_name = ""

    if user_id:
        try:
            user = InvitedUser.objects.get(id=user_id)
            user_name = user.name  # Adjust field name if different
        except InvitedUser.DoesNotExist:
            pass

    if request.method == "POST":
        try:
            client_item = request.POST.get("client_item")
            product_item = request.POST.get("product_item")
            ship_date = request.POST.get("ship_date")
            qty_shipped = int(request.POST.get("qty_shipped") or 0)
            supplier = request.POST.get("supplier")
            tracking_info = request.POST.get("tracking_info")
            expected_arrival_date = request.POST.get('expected_arrival_date')

            # Save the shipping entry
            Shipping.objects.create(
                client_id=client_item,
                item=product_item,
                ship_date=ship_date,
                ship_qty=qty_shipped,
                supplier=supplier,
                bol=tracking_info,
                checked_by=user,
                expected_arrival_date = expected_arrival_date
            )

            # Update Inventory
            inventory = Inventory.objects.filter(client_id=client_item, item=product_item).first()
            if inventory:
                inventory.qty_ordered = (inventory.qty_ordered or 0) + qty_shipped
                inventory.save()

            messages.success(request, "Shipment submitted and inventory updated!")
            return redirect("inventory_shipment")

        except Exception as e:
            messages.error(request, f"Error submitting shipment: {str(e)}")

    return render(request, "inventory_shipment.html", {"user_name": user_name})

@session_login_required
def get_product_item_num(request):
    clientId = request.GET.get("room_number")
    try:
        client_data_fetched = ProductData.objects.get(client_id__iexact=clientId)
        get_item = client_data_fetched.item if client_data_fetched.item else ""
        supplier = client_data_fetched.supplier if client_data_fetched.supplier else "N.A."
        return JsonResponse({"success": True, "room_type": get_item, "supplier": supplier})
    except RoomData.DoesNotExist:
        return JsonResponse({"success": False})


@session_login_required
def inventory_received(request):
    user_id = request.session.get("user_id")
    user_name = ""
    user = None

    if user_id:
        try:
            user = InvitedUser.objects.get(id=user_id)
            user_name = user.name
        except InvitedUser.DoesNotExist:
            pass

    if request.method == "POST":
        try:
            client_item = request.POST.get("client_item")
            product_item = request.POST.get("product_item")
            received_date = request.POST.get("received_date")
            received_qty = int(request.POST.get("received_qty") or 0)
            damaged_qty = int(request.POST.get("damaged_qty") or 0)

            InventoryReceived.objects.create(
                client_id=client_item,
                item=product_item,
                received_date=received_date,
                received_qty=received_qty,
                damaged_qty=damaged_qty,
                checked_by=user
            )

            # Update Inventory
            inventory = Inventory.objects.filter(client_id=client_item, item=product_item).first()
            if inventory:
                inventory.qty_received = (inventory.qty_received or 0) + (received_qty - damaged_qty)
                inventory.quantity_available = (inventory.quantity_available or 0) + (received_qty - damaged_qty)
                inventory.save()

            messages.success(request, "Inventory received successfully!")
            return redirect("inventory_received")

        except Exception as e:
            messages.error(request, f"Error saving received inventory: {str(e)}")

    return render(request, "inventory_received.html", {"user_name": user_name})

@session_login_required
def inventory_pull(request):
    
    user_id = request.session.get("user_id")
    user_name = ""

    if user_id:
        try:
            user = InvitedUser.objects.get(id=user_id)
            user_name = user.name
        except InvitedUser.DoesNotExist:
            pass
    if request.method == "POST":
        try:
            # Get all product IDs from the form
            product_ids = [key.split('_')[1] for key in request.POST.keys() if key.startswith('product_') and request.POST[key] == 'on']
            print("product_ids ::", product_ids)

            for product_id in product_ids:
                # Get the product room model
                prm = ProductData.objects.get(id=product_id)
                print("prm ::", prm)
                qty_pulled_value = int(request.POST.get(f'qty_pulled_{product_id}'))
                print("qty_pulled_value ::", qty_pulled_value)
                # Get the inventory item
                inventory = Inventory.objects.get(client_id=prm.client_id)
                print("inventory ::", inventory)
                print("inventory.quantity_available ::", inventory.quantity_available, type(inventory.quantity_available))
                print("qty_pulled_value ::", qty_pulled_value, type(qty_pulled_value))
                # Update inventory quantity
                inventory.quantity_available -= qty_pulled_value
                inventory.save()
                print("Before save ::",prm.client_id,prm.item,prm.id,qty_pulled_value,request.session.get('user_id'),request.POST.get(f'date_{product_id}'),request.POST.get('floor_number'),inventory.quantity_available,inventory.quantity_available - qty_pulled_value)
                # Create inventory pull record
                PullInventory.objects.create(
                    client_id=prm.client_id,
                    item = prm.item,
                    qty_pulled=qty_pulled_value,
                    pulled_by=user,
                    pulled_date=request.POST.get(f'date_{product_id}'),
                    floor=request.POST.get('floor_number'),
                    available_qty=inventory.quantity_available,
                    qty_available_after_pull=inventory.quantity_available - qty_pulled_value
                )
            
            messages.success(request, "Inventory pull completed successfully!")
            return redirect('inventory_pull')
            
        except Exception as e:
            messages.error(request, f"Error processing inventory pull: {str(e)}")
            return redirect('inventory_pull')
            
    return render(request, "inventory_pull.html", {
        "user_name": user_name
    })

@session_login_required
def inventory_received_item_num(request):
    clientId = request.GET.get("client_item")
    try:
        client_data_fetched = Inventory.objects.get(client_id__iexact=clientId)
        get_item = client_data_fetched.item if client_data_fetched.item else ""
        return JsonResponse({"success": True, "product_item": get_item})
    except RoomData.DoesNotExist:
        return JsonResponse({"success": False})


@login_required
def save_admin_installation(request):
    if request.method == "POST":
        installation_id = request.POST.get("installation_id")
        print("[hello]", installation_id)
        room = request.POST.get("room", "").strip()
        product_available = request.POST.get("product_available", "").strip()
        prework = request.POST.get("prework", "").strip()
        install = request.POST.get("install", "").strip()
        post_work = request.POST.get("post_work", "").strip()
        day_install_began = request.POST.get("day_install_began", "").strip()
        day_install_complete = request.POST.get("day_install_complete", "").strip()

        if not room:
            return JsonResponse({"error": "Room field is required."}, status=400)
        try:
            if installation_id:
                print("inside")
                installation = Installation.objects.get(id=installation_id)
                installation.room = room
                installation.product_available = product_available
                installation.prework = prework
                installation.install = install
                installation.post_work = post_work
                installation.day_install_began = parse_date(day_install_began)
                installation.day_install_complete = parse_date(day_install_complete)
                installation.save()
            else:
                print("Adding new row")
                Installation.objects.create(
                    room=room,
                    product_available=product_available,
                    prework=prework,
                    install=install,
                    post_work=post_work,
                    day_install_began=parse_date(day_install_began),
                    day_install_complete=parse_date(day_install_complete),
                )

            return JsonResponse({"success": True})

        except Installation.DoesNotExist:
            return JsonResponse({"error": "Installation not found."}, status=404)

    return JsonResponse({"error": "Invalid request"}, status=400)


@login_required
def save_schedule(request):
    if request.method == "POST":
        post_data = request.POST
        print(123)
        schedule_id = post_data.get("schedule_id") or ""
        phase = post_data.get("phase") or ""
        floor = post_data.get("floor") or ""
        production_starts = post_data.get("production_starts") or ""
        production_ends = post_data.get("production_ends") or ""
        shipping_depature = post_data.get("shipping_depature") or ""
        shipping_arrival = post_data.get("shipping_arrival") or ""
        custom_clearing_starts = post_data.get("custom_clearing_starts") or ""
        custom_clearing_ends = post_data.get("custom_clearing_ends") or ""
        arrive_on_site = post_data.get("arrive_on_site") or ""
        pre_work_starts = post_data.get("pre_work_starts") or ""
        pre_work_ends = post_data.get("pre_work_ends") or ""
        install_starts = post_data.get("install_starts") or ""
        install_ends = post_data.get("install_ends") or ""
        post_work_starts = post_data.get("post_work_starts") or ""
        post_work_ends = post_data.get("post_work_ends") or ""
        floor_completed = post_data.get("floor_completed") or ""
        floor_closes = post_data.get("floor_closes") or ""
        floor_opens = post_data.get("floor_opens") or ""
        print("333")
        try:
            if schedule_id:
                print("Editing ", custom_clearing_ends)
                installation = Schedule.objects.get(id=schedule_id)
                installation.phase = phase
                installation.floor = floor
                installation.production_starts = parse_date(production_starts)
                installation.production_ends = parse_date(production_ends)
                installation.shipping_depature = parse_date(shipping_depature)
                installation.shipping_arrival = parse_date(shipping_arrival)
                installation.custom_clearing_starts = parse_date(custom_clearing_starts)
                installation.custom_clearing_ends = parse_date(custom_clearing_ends)
                installation.arrive_on_site = parse_date(arrive_on_site)
                installation.pre_work_starts = parse_date(pre_work_starts)
                installation.pre_work_ends = parse_date(pre_work_ends)
                installation.install_starts = parse_date(install_starts)
                installation.install_ends = parse_date(install_ends)
                installation.post_work_starts = parse_date(post_work_starts)
                installation.post_work_ends = parse_date(post_work_ends)
                installation.floor_completed = parse_date(floor_completed)
                installation.floor_closes = parse_date(floor_closes)
                installation.floor_opens = parse_date(floor_opens)
                installation.save()
            else:
                print("under new")
                print(post_data)
                Schedule.objects.create(
                    phase=phase,
                    floor=floor,
                    production_starts=parse_date(production_starts),
                    production_ends=parse_date(production_ends),
                    shipping_depature=parse_date(shipping_depature),
                    shipping_arrival=parse_date(shipping_arrival),
                    custom_clearing_starts=parse_date(custom_clearing_starts),
                    custom_clearing_ends=parse_date(custom_clearing_ends),
                    arrive_on_site=parse_date(arrive_on_site),
                    pre_work_starts=parse_date(pre_work_starts),
                    pre_work_ends=parse_date(pre_work_ends),
                    install_starts=parse_date(install_starts),
                    install_ends=parse_date(install_ends),
                    post_work_starts=parse_date(post_work_starts),
                    post_work_ends=parse_date(post_work_ends),
                    floor_completed=parse_date(floor_completed),
                    floor_closes=parse_date(floor_closes),
                    floor_opens=parse_date(floor_opens),
                )
            return JsonResponse({"success": True})

        except Installation.DoesNotExist:
            return JsonResponse({"error": "Installation not found."}, status=404)

    return JsonResponse({"error": "Invalid request"}, status=400)


@login_required
def save_product_data(request):
    if request.method == "POST":
        post_data = request.POST
        print("hhhhhhhh", post_data)

        product_id = post_data.get("product_id")
        item = post_data.get("item", "").strip()
        client_id = post_data.get("client_id", "").strip()
        description = post_data.get("description") or 0

        supplier = post_data.get("supplier")
        client_selected = post_data.get("client_selected") or 0
        try:
            if product_id:
                print("inside")
                installation = ProductData.objects.get(id=product_id)
                installation.product_id = product_id
                installation.item = item
                installation.client_id = client_id
                installation.description = description
                installation.supplier = supplier
                installation.client_selected = client_selected
                installation.save()
            else:
                print("Adding new row")
                ProductData.objects.create(
                    item=item,
                    client_id=client_id,
                    description=description,
                    supplier=supplier,
                    client_selected=client_selected,
                )

            return JsonResponse({"success": True})

        except Installation.DoesNotExist:
            return JsonResponse({"error": "Installation not found."}, status=404)

    return JsonResponse({"error": "Invalid request"}, status=400)


@login_required
def delete_installation(request):
    if request.method == "POST":
        model_id = request.POST.get("model_id")
        try:
            room_model = Installation.objects.get(id=model_id)
            room_model.delete()
            return JsonResponse({"success": "Room Model deleted."})
        except Installation.DoesNotExist:
            return JsonResponse({"error": "Room Model not found."})
    return JsonResponse({"error": "Invalid request."})


@session_login_required
def user_logout(request):
    request.session.flush()
    return redirect("user_login")


@session_login_required
def home(request):
    user_id = request.session.get("user_id")

    if not user_id:
        return redirect("user_login")

    try:
        user = InvitedUser.objects.get(id=user_id)

        # Ensure roles are processed and stored in session for use in base template
        user_roles = []
        if user.role:
             # Handle potential string representation of list
            roles_raw = user.role
            if isinstance(roles_raw, str):
                try:
                    # Attempt to parse string as list (e.g., "['admin', 'inventory']")
                    parsed_roles = ast.literal_eval(roles_raw)
                    if isinstance(parsed_roles, list):
                        roles_raw = parsed_roles
                    else:
                        # Handle simple comma-separated string (e.g., "admin, inventory")
                        roles_raw = [r.strip() for r in roles_raw.split(',')]
                except (ValueError, SyntaxError):
                     # Fallback for simple comma-separated string if literal_eval fails
                     roles_raw = [r.strip() for r in roles_raw.split(',')]
            
            # Ensure it's a list and process
            if isinstance(roles_raw, list):
                 user_roles = [
                    role.strip().lower() for role in roles_raw if isinstance(role, str)
                ]
            
        # Store processed roles in session
        request.session['user_roles'] = user_roles 

        return render(
            request, "home.html", {"name": user.name, "roles": user_roles}
        )
    except InvitedUser.DoesNotExist:
        # Clear potentially invalid session data if user doesn't exist
        request.session.flush()
        return redirect("user_login")

@session_login_required
def installation_form(request):
    if not request.session.get("user_id"):
        messages.warning(request, "You must be logged in to access the form.")
        return redirect("user_login")

    invited_user = request.session.get("user_id")
    invited_user_instance = get_object_or_404(InvitedUser, id=invited_user)

    if request.method == "POST":
        room_number = request.POST.get("room_number")

        room_instance = get_object_or_404(RoomData, room=room_number)
        installation, _ = Installation.objects.get_or_create(room=room_instance.room)

        for key in request.POST:
            if key.startswith("step_"):
                parts = key.split("_")  # ['step', 'type', 'id']
                if len(parts) != 3:
                    continue
                _, step_type, step_id_str = parts

                try:
                    step_id = int(step_id_str)
                except ValueError:
                    continue

                is_checked = request.POST.get(key) == "on"
                date = request.POST.get(f"date_{step_type}_{step_id}") or now().date()

                if step_type == "installation":
                    if step_id == 0:  # Pre-Work completed
                        installation.prework = "YES" if is_checked else "NO"
                        installation.prework_check_on = date if is_checked else None
                        installation.prework_checked_by = invited_user_instance if is_checked else None
                        # Update day_install_began when pre-work is completed
                        if is_checked:
                            installation.day_install_began = date
                    elif step_id == 1:
                        installation.product_arrived_at_floor = "YES" if is_checked else "NO"
                        installation.product_arrived_at_floor_check_on = date if is_checked else None
                        installation.product_arrived_at_floor_checked_by = invited_user_instance if is_checked else None
                    elif step_id == 12:
                        installation.retouching = "YES" if is_checked else "NO"
                        installation.retouching_check_on = date if is_checked else None
                        installation.retouching_checked_by = invited_user_instance if is_checked else None
                    elif step_id == 13:  # Post Work
                        installation.post_work = "YES" if is_checked else "NO"
                        installation.post_work_check_on = date if is_checked else None
                        installation.post_work_checked_by = invited_user_instance if is_checked else None
                        # Update day_install_complete and install when post-work is completed
                        if is_checked:
                            installation.day_install_complete = date
                            installation.install = "YES"

                elif step_type == "detail":
                    try:
                        product_room_model = ProductRoomModel.objects.get(id=step_id)

                        install_detail, _ = InstallDetail.objects.get_or_create(
                            install_id=step_id,
                            defaults={
                                "product_id": product_room_model.product_id,
                                "room_model_id": product_room_model.room_model_id,
                                "room_id": room_instance.id,
                            }
                        )

                        if is_checked:
                            install_detail.status = "YES"
                            install_detail.installed_on = date
                            install_detail.installed_by = invited_user_instance
                        else:
                            install_detail.status = "NO"
                            install_detail.installed_on = None
                            install_detail.installed_by = None

                        install_detail.save()
                    except ProductRoomModel.DoesNotExist:
                        pass


        installation.save()
        messages.success(request, "Installation data saved successfully!")
        return redirect("installation_form")

    return render(request, "installation_form.html", {
        "invited_user": invited_user_instance,
    })

def parse_date(date_str):
    try:
        return datetime.strptime(date_str.strip(), "%Y-%m-%d") if date_str and date_str.strip() else None
    except ValueError:
        return None

@login_required
def chat_history(request):
    sessions = ChatSession.objects.prefetch_related('chat_history').order_by('-created_at')
    return render(request, 'chat_history.html', {'sessions': sessions})

@login_required
def view_chat_history(request, session_id):
    session = get_object_or_404(ChatSession, id=session_id)
    chat_messages = session.chat_history.order_by('created_at')[:100]  # from related_name
    return render(request, 'view_chat_history.html', {
        'session': session,
        'chat_messages': chat_messages
    })

@login_required
def product_room_model_list(request):
    """
    Display a list of all product room model mappings with related data.
    """
    # Get all mappings with related data for efficient template rendering
    product_room_model_list = ProductRoomModel.objects.select_related('product_id', 'room_model_id').all()
    
    # Get products and room models for the dropdown in the add/edit form
    products = ProductData.objects.all()
    room_models = RoomModel.objects.all().order_by(Lower('room_model'))
    
    return render(request, "product_room_model_list.html", {
        "product_room_model_list": product_room_model_list,
        "products": products,
        "room_models": room_models
    })

@login_required
def save_product_room_model(request):
    """
    Add or update a product room model mapping.
    """
    if request.method == "POST":
        mapping_id = request.POST.get("mapping_id")
        product_id = request.POST.get("product_id")
        room_model_id = request.POST.get("room_model_id")
        quantity = request.POST.get("quantity", "1").strip()
        
        # Validate inputs
        if not product_id or not room_model_id:
            return JsonResponse({"error": "Product and Room Model are required"}, status=400)
            
        try:
            quantity = int(quantity)
            if quantity < 0:
                return JsonResponse({"error": "Quantity must be a positive number"}, status=400)
        except ValueError:
            return JsonResponse({"error": "Quantity must be a valid number"}, status=400)

        # Check for existing mappings with the same product and room model (avoid duplicates)
        existing_mapping = ProductRoomModel.objects.filter(
            product_id_id=product_id, 
            room_model_id_id=room_model_id
        )
        
        if mapping_id:
            existing_mapping = existing_mapping.exclude(id=mapping_id)
        
        if existing_mapping.exists():
            return JsonResponse(
                {"error": "A mapping for this product and room model already exists"}, 
                status=400
            )
        
        try:
            product = ProductData.objects.get(id=product_id)
            room_model = RoomModel.objects.get(id=room_model_id)
            
            if mapping_id:
                # Update existing mapping
                mapping = ProductRoomModel.objects.get(id=mapping_id)
                mapping.quantity = quantity
                mapping.save()
            else:
                # Create new mapping
                ProductRoomModel.objects.create(
                    product_id=product,
                    room_model_id=room_model,
                    quantity=quantity
                )
                
            return JsonResponse({"success": True})
            
        except (ProductData.DoesNotExist, RoomModel.DoesNotExist):
            return JsonResponse({"error": "Product or Room Model not found"}, status=404)
        except ProductRoomModel.DoesNotExist:
            return JsonResponse({"error": "Mapping not found"}, status=404)
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)
    
    return JsonResponse({"error": "Invalid request method"}, status=405)

@login_required
def delete_product_room_model(request):
    """
    Delete a product room model mapping.
    """
    if request.method == "POST":
        model_id = request.POST.get("model_id")
        
        try:
            mapping = ProductRoomModel.objects.get(id=model_id)
            mapping.delete()
            return JsonResponse({"success": True})
        except ProductRoomModel.DoesNotExist:
            return JsonResponse({"error": "Mapping not found"}, status=404)
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)
    
    return JsonResponse({"error": "Invalid request method"}, status=405)

@session_login_required
def get_floor_products(request):
    floor_number = request.GET.get("floor_number")
    try:
        # Use raw SQL query to get products with total quantity needed
        products = ProductData.objects.raw("""
            WITH room_counts AS (
                SELECT rm.id AS room_model_id, COUNT(*) AS room_count
                FROM room_data rd
                JOIN room_model rm ON rd.room_model_id = rm.id
                WHERE rd.floor = %s
                GROUP BY rm.id
            ),
            pulled_quantities AS (
                SELECT client_id, item, SUM(qty_pulled) as total_pulled
                FROM pull_inventory
                GROUP BY client_id, item
            )
            SELECT pd.id, pd.item, pd.client_id, pd.description, pd.supplier,
                   SUM(prm.quantity * rc.room_count) AS total_quantity_needed,
                   COALESCE(inv.quantity_installed, 0) AS quantity_installed,
                   COALESCE(inv.quantity_available, 0) AS available_qty,
                   COALESCE(pq.total_pulled, 0) AS pulled_quantity
            FROM product_room_model prm
            JOIN product_data pd ON prm.product_id = pd.id
            JOIN room_counts rc ON prm.room_model_id = rc.room_model_id
            LEFT JOIN inventory inv ON pd.client_id = inv.client_id
            LEFT JOIN pulled_quantities pq ON pd.client_id = pq.client_id AND pd.item = pq.item
            GROUP BY pd.id, pd.client_id, pd.description, pd.supplier, inv.quantity_installed, inv.quantity_available, pq.total_pulled
            ORDER BY pd.client_id
        """, [floor_number])
        
        result_products = []
        for product in products:
            # Calculate remaining quantity needed after subtracting already pulled quantity
            remaining_quantity = max(0, product.total_quantity_needed - product.pulled_quantity)
            
            result_products.append({
                "id": product.id,
                "client_id": product.client_id,
                "description": product.description,
                "quantity": remaining_quantity,  # Use remaining quantity instead of total
                "available_qty": product.available_qty,
                "supplier": product.supplier,
                "quantity_installed": product.quantity_installed,  # Add quantity already pulled
                "total_quantity_needed": product.total_quantity_needed,  # Keep original total for reference
                "pulled_quantity": product.pulled_quantity  # Add pulled quantity
            })
            
        return JsonResponse({
            "success": True,
            "products": result_products
        })
    except Exception as e:
        return JsonResponse({
            "success": False,
            "error": str(e)
        })

# Helper function to generate XLS response
def _generate_xls_response(data, filename, sheet_name="Sheet1"):
    response = HttpResponse(content_type='application/ms-excel')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'

    wb = xlwt.Workbook(encoding='utf-8')
    ws = wb.add_sheet(sheet_name)

    # Sheet header, first row
    row_num = 0
    font_style = xlwt.XFStyle()
    font_style.font.bold = True

    # Infer columns from the first dictionary in the list
    if data:
        columns = list(data[0].keys())
        for col_num, column_title in enumerate(columns):
            ws.write(row_num, col_num, column_title, font_style)

        # Sheet body, remaining rows
        font_style = xlwt.XFStyle()

        for row_data in data:
            row_num += 1
            for col_num, col_key in enumerate(columns):
                value = row_data.get(col_key, '')
                # Handle potential date/datetime objects if necessary
                if isinstance(value, (date, datetime)):
                    value = value.strftime('%Y-%m-%d %H:%M:%S') # Or just %Y-%m-%d
                ws.write(row_num, col_num, value, font_style)
    else:
         # Write a message if no data
         ws.write(0, 0, "No data found for the selected criteria.", font_style)


    wb.save(response)
    return response

# Helper function to get floor products data (extracted SQL)
def _get_floor_products_data(floor_number):
    try:
        with connection.cursor() as cursor:

            sql_query = """
             WITH room_counts AS (
                SELECT rm.id AS room_model_id, COUNT(*) AS room_count
                FROM room_data rd
                JOIN room_model rm ON rd.room_model_id = rm.id
                WHERE rd.floor = %s
                GROUP BY rm.id
            ),
            pulled_quantities AS (
                SELECT client_id, item, SUM(qty_pulled) as total_pulled
                FROM pull_inventory
                GROUP BY client_id, item
            )
            SELECT pd.id, pd.item, pd.client_id, pd.description, pd.supplier,
                   SUM(prm.quantity * rc.room_count) AS total_quantity_needed,
                   COALESCE(inv.quantity_installed, 0) AS quantity_installed,
                   COALESCE(inv.quantity_available, 0) AS available_qty,
                   COALESCE(pq.total_pulled, 0) AS pulled_quantity
            FROM product_room_model prm
            JOIN product_data pd ON prm.product_id = pd.id
            JOIN room_counts rc ON prm.room_model_id = rc.room_model_id
            LEFT JOIN inventory inv ON pd.client_id = inv.client_id
            LEFT JOIN pulled_quantities pq ON pd.client_id = pq.client_id AND pd.item = pq.item
            GROUP BY pd.id, pd.client_id, pd.description, pd.supplier, inv.quantity_installed, inv.quantity_available, pq.total_pulled
            ORDER BY pd.client_id"""
            
            print("sql_query",sql_query)
            cursor.execute(sql_query, [floor_number]) # Pass floor_number twice

            columns = [col[0] for col in cursor.description]
            products = [dict(zip(columns, row)) for row in cursor.fetchall()]

        result_products = []
        for product in products:
            total_needed = product.get('total_quantity_needed', 0) or 0
            pulled = product.get('pulled_quantity', 0) or 0
            remaining_quantity = max(0, total_needed - pulled)

            result_products.append({
                "id": product.get('id'),
                "item": product.get('item'),
                "client_id": product.get('client_id'),
                "description": product.get('description'),
                "supplier": product.get('supplier'),
                "total_quantity_needed": total_needed,
                "pulled_quantity": pulled,
                "remaining_quantity_needed": remaining_quantity, # Renamed from 'quantity' for clarity
                "available_qty": product.get('available_qty', 0) or 0,
                "quantity_installed": product.get('quantity_installed', 0) or 0,
            })
        return result_products
    except Exception as e:
        print(f"Error fetching floor products data: {e}")
        return []

# Helper function to get room products data
def _get_room_products_data(room_model_id):
    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT
                    pd.id, pd.item, pd.client_id, pd.description, pd.supplier,
                    prm.quantity AS quantity_needed_per_room,
                    COALESCE(inv.quantity_installed, 0) AS quantity_installed,
                    COALESCE(inv.quantity_available, 0) AS available_qty
                FROM product_room_model prm
                JOIN product_data pd ON prm.product_id = pd.id
                JOIN room_model rm ON prm.room_model_id = rm.id
                LEFT JOIN inventory inv ON pd.client_id = inv.client_id
                WHERE prm.room_model_id = %s
                ORDER BY pd.client_id;
            """, [room_model_id])

            columns = [col[0] for col in cursor.description]
            products = [dict(zip(columns, row)) for row in cursor.fetchall()]
        return products
    except Exception as e:
        print(f"Error fetching room products data: {e}")
        return []

@session_login_required
def floor_products_list(request):
    floor_number = request.GET.get('floor_number', '').strip()
    product_list = []
    error_message = None

    if floor_number:
        try:
            # Validate floor_number is an integer if necessary
            floor_number = int(floor_number) # Raises ValueError if not an integer
            print("floor_number",floor_number, type(floor_number))

            product_list = _get_floor_products_data(floor_number)
            if not product_list and request.GET: # Check if it was a search attempt
                 error_message = f"No products found for floor {floor_number}."

            # Handle XLS download request
            if request.GET.get('download') == 'xls':
                if product_list:
                    filename = f"products_list_for_{floor_number}_floor.xls"
                    return _generate_xls_response(product_list, filename, sheet_name=f"Floor {floor_number}")
                else:
                     # Optionally handle download request when no data
                     messages.warning(request, f"No data to download for floor {floor_number}.")
                     # Redirect or render template again
                     return redirect(request.path_info + f'?floor_number={floor_number}')


        except ValueError:
            error_message = "Invalid floor number entered. Please enter a number."
            floor_number = '' # Clear invalid input for template rendering
        except Exception as e:
            error_message = f"An error occurred: {str(e)}"
            print(f"Error in floor_products_list view: {e}")


    context = {
        'product_list': product_list,
        'floor_number': floor_number,
        'error_message': error_message,
    }
    return render(request, 'floor_products_list.html', context)


@session_login_required
def room_number_products_list(request):
    room_number = request.GET.get('room_number', '').strip()
    product_list = []
    error_message = None
    found_room = None
    room_model_name = None

    if room_number:
        try:
            # Find the room
            found_room = RoomData.objects.select_related('room_model_id').get(room=room_number)
            room_model_id = found_room.room_model_id.id if found_room.room_model_id else None
            room_model_name = found_room.room_model_id.room_model if found_room.room_model_id else "Unknown Model"

            if room_model_id:
                product_list = _get_room_products_data(room_model_id)
                if not product_list and request.GET:
                    error_message = f"No specific products configured for room model '{room_model_name}' (used by room {room_number})."
            else:
                error_message = f"Room {room_number} does not have an associated room model."
                product_list = [] # Ensure product list is empty

            # Handle XLS download request
            if request.GET.get('download') == 'xls' and room_model_id:
                if product_list:
                    filename = f"products_list_for_room_{room_number}_{room_model_name.replace(' ', '_')}.xls"
                    return _generate_xls_response(product_list, filename, sheet_name=f"Room {room_number} ({room_model_name})")
                else:
                    messages.warning(request, f"No product data to download for room {room_number} (Model: {room_model_name}).")
                    # Redirect back to the search page for the same room number
                    return redirect(request.path_info + f'?room_number={room_number}')
            elif request.GET.get('download') == 'xls' and not room_model_id:
                 messages.warning(request, f"Cannot download product list for room {room_number} as it has no associated model.")
                 return redirect(request.path_info + f'?room_number={room_number}')


        except RoomData.DoesNotExist:
             error_message = f"Room number '{room_number}' not found."
             room_number = '' # Clear invalid input
             product_list = [] # Ensure product list is empty
        except Exception as e:
             error_message = f"An error occurred: {str(e)}"
             print(f"Error in room_number_products_list view: {e}")
             product_list = [] # Ensure product list is empty


    context = {
        'product_list': product_list,
        'room_number': room_number, # Pass back the searched room number
        'found_room': found_room,
        'room_model_name': room_model_name,
        'error_message': error_message,
    }
    return render(request, 'room_products_list.html', context)

# --- Issue Tracking Views --- 
from django.contrib.auth.models import User

@session_login_required
def issue_list(request):
    user = get_object_or_404(InvitedUser, id=request.session.get("user_id"))
    print(f"DEBUG: Querying for user: ID={user.id}, Type={type(user)}, Name={user.name}")
    user_roles = user.role
    queryset = Issue.objects.filter(created_by=user).distinct()
    queryset = queryset.order_by('-created_at').select_related('created_by', 'assignee')
    context = {
        'issues': queryset,
        'user_roles': user_roles
    }
    return render(request, 'issues/issue_list.html', context)

from .forms import CommentForm

@session_login_required
def issue_detail(request, issue_id):
    issue = get_object_or_404(Issue.objects.select_related('created_by', 'assignee').prefetch_related('observers', 'comments__user'), id=issue_id)
    print("\n\n\n\n",request.session.get("user_id"))
    user = get_object_or_404(InvitedUser, id=request.session.get("user_id"))
    user_roles = getattr(user, 'role', [])

    can_view = False
    if 'admin' in user_roles or ('hotel_admin' in user_roles and issue.is_for_hotel_admin) or \
       user == issue.created_by or user == issue.assignee or user in issue.observers.all():
        can_view = True
        
    if not can_view:
        messages.error(request, "You do not have permission to view this issue.")
        return redirect('issue_list')

    can_comment = False
    if 'admin' in user_roles or ('hotel_admin' in user_roles and issue.is_for_hotel_admin) or \
       user == issue.created_by or user == issue.assignee or user in issue.observers.all():
        can_comment = True

    if request.method == 'POST':
        if not can_comment:
            messages.error(request, "You do not have permission to comment on this issue.")
            # Redirect or render with error, avoid processing form
            return redirect('issue_detail', issue_id=issue.id)
            
        comment_form = CommentForm(request.POST, request.FILES) 
        if comment_form.is_valid():
            new_comment = comment_form.save(commit=False)
            new_comment.issue = issue
            new_comment.user = user
            
            media_data_for_json = []
            
            # Process uploaded images from cleaned_data
            uploaded_images = comment_form.cleaned_data.get('images', [])
            for image_file in uploaded_images:
                # Ensure a unique filename to prevent overwrites
                unique_filename = f"issues/comments/images/{issue.id}/{uuid.uuid4()}_{image_file.name}"
                file_path = default_storage.save(unique_filename, image_file)
                file_url = default_storage.url(file_path)
                media_data_for_json.append({
                    'type': 'image',
                    'url': file_url,
                    'name': image_file.name,
                    'size': image_file.size
                })

            # Process uploaded video from cleaned_data
            uploaded_video = comment_form.cleaned_data.get('video', None)
            if uploaded_video:
                unique_filename = f"issues/comments/videos/{issue.id}/{uuid.uuid4()}_{uploaded_video.name}"
                file_path = default_storage.save(unique_filename, uploaded_video)
                file_url = default_storage.url(file_path)
                media_data_for_json.append({
                    'type': 'video',
                    'url': file_url,
                    'name': uploaded_video.name,
                    'size': uploaded_video.size
                })
            
            new_comment.media = media_data_for_json # Store the list of dicts
            new_comment.save()
            messages.success(request, "Comment added successfully.")
            return redirect('issue_detail', issue_id=issue.id)
        else:
            messages.error(request, "Please correct the errors in your comment.")
    else:
        comment_form = CommentForm()

    comments = issue.comments.all().order_by('created_at')

    context = {
        'issue': issue,
        'comments': comments,
        'comment_form': comment_form,
        'can_comment': can_comment,
        'user_roles': user_roles
    }
    return render(request, 'issues/issue_detail.html', context)

from django.core.files.storage import default_storage
import uuid
import os

@session_login_required
def issue_create(request):
    user = get_object_or_404(InvitedUser, id=request.session.get("user_id"))

    if request.method == 'POST':
        logger.debug(f"Request FILES: {request.FILES}")
        form = IssueForm(request.POST, request.FILES)
        if form.is_valid():
            issue = form.save(commit=False)
            issue.created_by = user
            issue.save()
            issue.observers.add(user)

            logger.info(f"Issue created by {user.name} with ID {issue.id}")
            logger.info(f"Issue observers: {issue.observers.all()}")

            # Process and save media files
            media_urls = []
            images = form.cleaned_data.get('images', [])
            video = form.cleaned_data.get('video')

            # Save images
            for image in images:
                file_name = default_storage.save(f"issues/images/{uuid.uuid4()}_{image.name}", image)
                file_url = default_storage.url(file_name)
                media_urls.append({'type': 'image', 'url': file_url, 'size': image.size, 'name': image.name})

            # Save video
            if video:
                file_name = default_storage.save(f"issues/videos/{uuid.uuid4()}_{video.name}", video)
                file_url = default_storage.url(file_name)
                media_urls.append({'type': 'video', 'url': file_url, 'size': video.size, 'name':video.name})

            # Save initial comment with media info
            Comment.objects.create(
                issue=issue,
                user=user,
                text_content=form.cleaned_data['initial_comment'],
                media=media_urls
            )

            success_message = f"Issue #{issue.id} created successfully."
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': True,
                    'message': success_message,
                    'redirect_url': reverse('issue_detail', kwargs={'issue_id': issue.id})
                })
            else:
                messages.success(request, success_message)
                return redirect('issue_detail', issue_id=issue.id)
        else:
            logger.error(f"Form errors: {form.errors.as_json()}")
            error_message = "Please correct the errors below."
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': False,
                    'message': error_message,
                    'errors': json.loads(form.errors.as_json())  # Parse JSON string to dict
                }, status=400)
            else:
                messages.error(request, error_message)
    else:
        form = IssueForm()

    return render(request, 'issues/issue_form.html', {'form': form})
# --- Admin-specific Issue Views --- 

def is_admin(user):

    try:
        return 'admin' in user.role
    except Exception as e:
        return 'admin'
        
    #     user_data = User.objects.get(email=user.email)
            
# @user_passes_test(is_admin, login_url='/user_login/')
@session_login_required
def admin_issue_list(request):
    if request.user.is_authenticated:
        if request.user.is_superuser:
            logger.info("\n\n\n\nAdmin Issue List")
            issue_list_all = Issue.objects.all().order_by('-created_at').select_related('created_by', 'assignee')
            paginator = Paginator(issue_list_all, 25)
            page_number = request.GET.get('page')
            try:
                issues_page = paginator.page(page_number)
            except PageNotAnInteger:
                issues_page = paginator.page(1)
            except EmptyPage:
                issues_page = paginator.page(paginator.num_pages)
            context = {
                'issues_page': issues_page,
            }
            return render(request, 'issues/admin_issue_list.html', context)


@user_passes_test(is_admin, login_url='/user_login/')
@session_login_required
def admin_issue_edit(request, issue_id):
    issue = get_object_or_404(Issue, pk=issue_id)
    user = get_object_or_404(InvitedUser, id=request.session.get("user_id"))
    if request.method == 'POST':
        form = IssueUpdateForm(request.POST, instance=issue)
        if form.is_valid():
            updated_observers = form.cleaned_data.get('observers')
            if issue.created_by not in updated_observers:
                updated_observers |= InvitedUser.objects.filter(pk=issue.created_by.pk)
                form.instance.observers.set(updated_observers)
            form.save()
            messages.success(request, f"Issue #{issue.id} updated successfully.")
            return redirect('admin_issue_list')
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = IssueUpdateForm(instance=issue)
    context = {
        'form': form,
        'issue': issue
    }
    return render(request, 'issues/admin_issue_form.html', context)



@session_login_required
def comment_create(request, issue_id):
    user = get_object_or_404(InvitedUser, id=request.session.get("user_id"))
    issue = get_object_or_404(Issue, id=issue_id)

    if request.method == 'POST':
        logger.debug(f"Request FILES: {request.FILES}")
        form = CommentForm(request.POST, request.FILES)
        if form.is_valid():
            comment = form.save(commit=False)
            comment.user = user
            comment.issue = issue
            comment.save()

            # Process and save media files
            media_urls = []
            images = form.cleaned_data.get('images', [])
            video = form.cleaned_data.get('video')

            # Save images
            for image in images:
                file_name = default_storage.save(f"comments/images/{uuid.uuid4()}_{image.name}", image)
                file_url = default_storage.url(file_name)
                media_urls.append({'type': 'image', 'url': file_url, 'size': image.size, 'name': image.name})

            # Save video
            if video:
                file_name = default_storage.save(f"comments/videos/{uuid.uuid4()}_{video.name}", video)
                file_url = default_storage.url(file_name)
                media_urls.append({'type': 'video', 'url': file_url, 'size': video.size, 'name': video.name})

            # Update comment with media URLs
            comment.media = media_urls
            comment.save()

            success_message = "Comment added successfully."
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': True,
                    'message': success_message,
                    'redirect_url': reverse('issue_detail', kwargs={'issue_id': issue.id})
                })
            else:
                messages.success(request, success_message)
                return redirect('issue_detail', issue_id=issue.id)
        else:
            logger.error(f"Form errors: {form.errors.as_json()}")
            error_message = "Please correct the errors below."
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': False,
                    'message': error_message,
                    'errors': json.loads(form.errors.as_json())
                }, status=400)
            else:
                messages.error(request, error_message)
    else:
        form = CommentForm()

    return render(request, 'issues/comment_form.html', {'form': form, 'issue': issue})