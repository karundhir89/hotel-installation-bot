import ast
import json
import random
import string
from datetime import date, datetime
from functools import wraps
from .forms import CommentForm
import uuid
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
from django.core.files.storage import default_storage
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
import pytz

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
from django.contrib.contenttypes.models import ContentType # Added for GFK
from django.utils.timezone import make_aware

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

        # Check if email already exists
        if InvitedUser.objects.filter(email=email).exists():
            return JsonResponse({"error": "User with this email already exists."}, status=400)


        user = InvitedUser.objects.create(
            name=name,
            role=roles_list,
            last_login=now(),
            email=email,
            status=status if status else 'activated', # Default to activated if not provided
            password=bcrypt.hashpw(password.encode(), bcrypt.gensalt()),
        )

        if 'admin' in roles_list:
            auth_user = User.objects.create_user(
                username=email,
                password=password,
                email=email,
            )
            auth_user.is_superuser = False
            auth_user.save()
        

    return render(request, "add_users_roles.html") # Should not be reached if AJAX

@login_required
def edit_users_roles(request, user_id):
    if request.method == "POST":
        try:
            print("edit_users_roles user_id::", user_id)
            user = get_object_or_404(InvitedUser, id=user_id)
            
            name = request.POST.get("name")
            email = request.POST.get("email")
            roles = request.POST.get("role")
            status = request.POST.get("status")
            password = request.POST.get("password")

            roles_list = roles.split(", ") if roles else []

            # Check if email is being changed and if the new email already exists for another user
            if email != user.email and InvitedUser.objects.filter(email=email).exclude(id=user_id).exists():
                return JsonResponse({"error": "Another user with this email already exists."}, status=400)

            user.name = name
            user.email = email
            user.role = roles_list
            user.status = status if status else 'activated' # Default to activated

            if password: # Only update password if a new one is provided
                user.password = bcrypt.hashpw(password.encode(), bcrypt.gensalt())
            
            user.save()

            if 'admin' in roles_list:
                auth_user = User.objects.create_user(
                    username=email,
                    password=password,
                    email=email,
                )
                auth_user.is_superuser = False
                auth_user.save()
            else:
                try:
                    auth_user = User.objects.get(username=email)
                    auth_user.delete()
                except User.DoesNotExist:
                    pass
            return JsonResponse({"message": "User updated successfully!"})

        except InvitedUser.DoesNotExist:
            return JsonResponse({"error": "User not found."}, status=404)
        except Exception as e:
            logger.error(f"Error editing user {user_id}: {e}", exc_info=True)
            return JsonResponse({"error": f"An error occurred: {str(e)}"}, status=500)
    
    # GET request to this URL isn't typical for AJAX forms but could render a form if needed.
    # For now, redirect or return error for GET.
    return JsonResponse({"error": "Invalid request method. Only POST is allowed for editing."}, status=405)

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
    install_query = Installation.objects.select_related(
        'prework_checked_by',
        'post_work_checked_by',
        'product_arrived_at_floor_checked_by',
        'retouching_checked_by'
    ).all()

    # Get all distinct floor numbers from RoomData for the filter dropdown
    all_floors = RoomData.objects.order_by('floor').values_list('floor', flat=True).distinct()
    selected_floor = request.GET.get('floor')

    if selected_floor:
        try:
            selected_floor_int = int(selected_floor)
            # Filter installations by room numbers that are on the selected floor
            rooms_on_floor = RoomData.objects.filter(floor=selected_floor_int).values_list('room', flat=True)
            install_query = install_query.filter(room__in=rooms_on_floor)
        except ValueError:
            # Handle cases where floor parameter is not a valid integer, maybe show a message or ignore
            pass

    install = list(install_query) # Execute the query

    # Create a mapping of room numbers to their floors
    room_to_floor_map = {rd.room: rd.floor for rd in RoomData.objects.filter(room__in=[i.room for i in install])}

    # Convert the dates to a proper format and add floor information
    for installation in install:
        installation.floor = room_to_floor_map.get(installation.room) # Add floor to installation object
        if installation.day_install_began:
            installation.formatted_day_install_began = installation.day_install_began.strftime('%Y-%m-%d')
            installation.day_install_began = installation.day_install_began.strftime('%m-%d-%Y')
        if installation.day_install_complete:
            installation.formatted_day_install_complete = installation.day_install_complete.strftime('%Y-%m-%d')
            installation.day_install_complete = installation.day_install_complete.strftime('%m-%d-%Y')
        if installation.prework_check_on:
            installation.formatted_prework_check_on = installation.prework_check_on.strftime('%Y-%m-%d')
            installation.prework_check_on = installation.prework_check_on.strftime('%m-%d-%Y')
        if installation.post_work_check_on:
            installation.formatted_post_work_check_on = installation.post_work_check_on.strftime('%Y-%m-%d')
            installation.post_work_check_on = installation.post_work_check_on.strftime('%m-%d-%Y')
        if installation.retouching_check_on:
            installation.formatted_retouching_check_on = installation.retouching_check_on.strftime('%Y-%m-%d')
            installation.retouching_check_on = installation.retouching_check_on.strftime('%m-%d-%Y')
        if installation.product_arrived_at_floor_check_on:
            installation.formatted_product_arrived_at_floor_check_on = installation.product_arrived_at_floor_check_on.strftime('%Y-%m-%d')
            installation.product_arrived_at_floor_check_on = installation.product_arrived_at_floor_check_on.strftime('%m-%d-%Y')
    
    # Pass the modified install data and floor filter data to the template
    context = {
        "install": install,
        "all_floors": all_floors,
        "selected_floor": selected_floor
    }
    return render(request, "install.html", context)


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

def _get_installation_checklist_data(room_number, installation_id=None, user_for_prefill=None):
    """
    Helper function to get installation checklist items and saved data.
    Can be used by both frontend and admin views.
    If installation_id is provided, it fetches data for that specific installation.
    Otherwise, it behaves like the original get_room_type for a given room_number.
    """
    try:
        room_data = RoomData.objects.select_related('room_model_id').get(room=room_number)
        room_type = room_data.room_model_id.room_model if room_data.room_model_id else ""
        room_model_instance = room_data.room_model_id

        if not room_model_instance:
            return {"success": False, "message": "Room model not found for this room."}

        # Determine the Installation instance
        if installation_id:
            installation_data = get_object_or_404(Installation, id=installation_id, room=room_number)
        else: # Original behavior for frontend form if no specific installation_id
            installation_data, _ = Installation.objects.get_or_create(
                room=room_data.room, # Use room_data.room (integer)
                defaults={ # Sensible defaults if creating
                    'prework': "NO",
                    'product_arrived_at_floor': "NO",
                    'retouching': "NO",
                    'post_work': "NO",
                }
            )
            # If created, it won't have an ID until saved. If fetched, it has one.
            # If it was just created, its ID might be None until a subsequent save by the form.
            # This is fine, as InstallDetail items will be created linked to this potential new installation.


        # Fetch products associated with the room model
        product_room_models = ProductRoomModel.objects.filter(
            room_model_id=room_model_instance.id
        ).select_related('product_id')

        saved_items = []
        check_items = [] # This will be the final list of all items (installation + details)

        # Fetch existing InstallDetail items for this installation
        # Ensure installation_data.id is valid before querying
        existing_install_details = []
        if installation_data and installation_data.id:
            existing_install_details = InstallDetail.objects.filter(
                installation_id=installation_data.id,
                room_id=room_data.id
            ).select_related("product_id", "installed_by")

        # Create a map of existing install details for quick lookup
        existing_details_map = {
            detail.product_id_id: detail for detail in existing_install_details
        }

        install_details_to_create_or_update = []

        for prm in product_room_models:
            product = prm.product_id
            install_detail_item = existing_details_map.get(product.id)

            if not install_detail_item and installation_data and installation_data.id : # Only create if an installation record exists
                # This product is in the room model but not yet in InstallDetail for this installation
                install_detail_item = InstallDetail(
                    installation_id=installation_data.id, # Link to existing/created Installation
                    product_id=product,
                    room_id=room_data,
                    room_model_id=room_model_instance,
                    product_name=product.description or product.item, # Ensure product_name is set
                    status="NO" # Default status
                )
                # We can't bulk_create and then get IDs immediately if some items are new and installation_data was just created (no ID yet)
                # Instead, we'll prepare them. If installation_data has an ID, we save.
                # This part is tricky if installation_data was just created and doesn't have an ID.
                # For admin edit, installation_data.id will always exist.
                # For frontend, if InstallDetail items are crucial *before* first save, this needs care.
                # Assuming for now that if InstallDetail are created, installation_data.id is valid.
                if installation_data.id: # Ensure main installation record has an ID
                    install_detail_item.save() # Save to get an install_id (PK)
                    existing_details_map[product.id] = install_detail_item # Add to map
                else:
                    # If installation record is new (no ID), these won't be saved yet.
                    # This scenario is more for the initial GET in the frontend form.
                    # They will be properly created during the POST save.
                    pass # Defer creation to the POST if main installation is new.

            # print(f"install_detail_item: {install_detail_item}")
            # Prepare data for saved_items and check_items
            if install_detail_item: # If it exists or was just saved
                saved_items.append({
                    "install_id": install_detail_item.install_id,
                    "product_id": product.id,
                    "product_name": install_detail_item.product_id.description,
                    "room_id": room_data.id,
                    "room_model_id": room_model_instance.id,
                    "product_room_model_id": prm.id, # ID of the ProductRoomModel mapping
                    "installed_by": install_detail_item.installed_by.name if install_detail_item.installed_by else None,
                    "installed_on": install_detail_item.installed_on.isoformat() if install_detail_item.installed_on else None,
                    "status": install_detail_item.status,
                    "product_client_id": product.client_id,
                })
                check_items.append({
                    "id": install_detail_item.install_id, # This is InstallDetail PK
                    "label": f"({product.client_id or 'N/A'}) - {install_detail_item.product_id.description}",
                    "type": "detail",
                    "status": install_detail_item.status,
                    "checked_by": install_detail_item.installed_by.name if install_detail_item.installed_by else None,
                    "check_on": localtime(install_detail_item.installed_on).isoformat() if install_detail_item.installed_on else None,
                })
            elif not installation_data.id : # Product from room model, but main installation record is new (no ID yet)
                 # This is for the initial rendering of the frontend form for a NEW installation
                 # Create temporary placeholder items
                check_items.append({
                    "id": f"newproduct_{product.id}", # Temporary ID for unsaved items
                    "label": f"({product.client_id or 'N/A'}) - {install_detail_item.product_id.description}",
                    "type": "detail",
                    "status": "NO", # Default
                    "checked_by": None,
                    "check_on": None,
                })


        # Add Installation-level static checklist items
        if installation_data: # This will always be true due to get_or_create or get_object_or_404
            static_install_items = [
                {
                    "id": 0, "label": "Pre-Work completed.",
                    "checked_by": installation_data.prework_checked_by.name if installation_data.prework_checked_by else None,
                    "check_on": localtime(installation_data.prework_check_on).isoformat() if installation_data.prework_check_on else None,
                    "status": installation_data.prework, "type": "installation"
                },
                {
                    "id": 1, "label": "The product arrived at the floor.",
                    "checked_by": installation_data.product_arrived_at_floor_checked_by.name if installation_data.product_arrived_at_floor_checked_by else None,
                    "check_on": localtime(installation_data.product_arrived_at_floor_check_on).isoformat() if installation_data.product_arrived_at_floor_check_on else None,
                    "status": installation_data.product_arrived_at_floor, "type": "installation"
                },
                {
                    "id": 12, "label": "Retouching.",
                    "checked_by": installation_data.retouching_checked_by.name if installation_data.retouching_checked_by else None,
                    "check_on": localtime(installation_data.retouching_check_on).isoformat() if installation_data.retouching_check_on else None,
                    "status": installation_data.retouching, "type": "installation"
                },
                {
                    "id": 13, "label": "Post Work.",
                    "checked_by": installation_data.post_work_checked_by.name if installation_data.post_work_checked_by else None,
                    "check_on": localtime(installation_data.post_work_check_on).isoformat() if installation_data.post_work_check_on else None,
                    "status": installation_data.post_work, "type": "installation"
                },
            ]
            check_items.extend(static_install_items)
        
        # Sort check_items: installation steps first, then details.
        # Within installation steps, sort by specific IDs (0,1 then 12,13)
        # Within detail steps, sort by label perhaps, or product ID.
        def sort_key(item):
            if item['type'] == 'installation':
                if item['id'] == 0: return (0, 0)
                if item['id'] == 1: return (0, 1)
                if item['id'] == 12: return (0, 12)
                if item['id'] == 13: return (0, 13)
                return (0, item['id']) # Should not happen with current static IDs
            else: # type == 'detail'
                # Ensure consistent sorting for details, e.g., by label
                return (1, item['label'])


        check_items = sorted(check_items, key=sort_key)

        return {
            "success": True,
            "room_type": room_type,
            "check_items": check_items, # This now contains both installation and detail types
            "saved_items": saved_items, # This primarily contains formatted InstallDetail data
            "installation_id": installation_data.id if installation_data else None,
            "room_id_for_installation": room_data.id, # Pass room_data.id for clarity
        }

    except RoomData.DoesNotExist:
        return {"success": False, "message": "Room not found"}
    except RoomModel.DoesNotExist:
        return {"success": False, "message": "Room model not found for this room"}
    except Installation.DoesNotExist:
        return {"success": False, "message": "Installation record not found"}
    except Exception as e:
        logger.error(f"Error in _get_installation_checklist_data for room {room_number}, install_id {installation_id}: {e}", exc_info=True)
        return {"success": False, "message": f"An unexpected error occurred: {str(e)}"}


# Define parse_date at the module level
def parse_date(date_str):
    try:
        return datetime.strptime(date_str.strip(), "%Y-%m-%d").date() if date_str and date_str.strip() else None
    except ValueError:
        try:
            # Fallback for datetime strings if time is included
            return datetime.strptime(date_str.strip(), "%Y-%m-%dT%H:%M:%S.%fZ").date() if date_str and date_str.strip() else None
        except ValueError:
            try:
                return datetime.strptime(date_str.strip(), "%Y-%m-%d %H:%M:%S").date() if date_str and date_str.strip() else None
            except ValueError:
                logger.warning(f"Could not parse date string: {date_str}")
                return None

@session_login_required
def get_room_type(request):
    room_number_str = request.GET.get("room_number")
    if not room_number_str:
        return JsonResponse({"success": False, "message": "Room number not provided."}, status=400)
    
    try:
        # Attempt to convert room_number to integer if your RoomData.room is an IntegerField
        room_number = int(room_number_str)
    except ValueError:
        return JsonResponse({"success": False, "message": "Invalid room number format."}, status=400)

    # Call the helper function
    # For the frontend form, we don't pass a specific installation_id initially,
    # the helper will do get_or_create for the Installation object.
    data = _get_installation_checklist_data(room_number=room_number)
    return JsonResponse(data)


def _save_installation_data(request_post_data, user_instance, room_number_str, installation_id_str=None):
    """
    Helper function to save installation data.
    Used by both frontend installation_form and admin_save_installation_details.
    `room_number_str` is used to fetch RoomData if installation_id is not provided or to verify.
    `installation_id_str` is explicitly passed for admin edits.
    """
    print(request_post_data)
            # Now use product_id, step_checked, etc.

    try:
        if not room_number_str:
            return {"success": False, "message": "Room number is required."}
        
        try:
            room_number_int = int(room_number_str)
            room_instance = get_object_or_404(RoomData, room=room_number_int)
        except ValueError:
            return {"success": False, "message": "Invalid room number format."}
        except RoomData.DoesNotExist:
            return {"success": False, "message": f"Room {room_number_str} not found."}

        # Determine the Installation instance
        if installation_id_str: # Admin edit or frontend if it was an existing installation
            installation_id = int(installation_id_str)
            installation_instance = get_object_or_404(Installation, id=installation_id, room=room_instance.room)
        else: # Frontend creating a new one or updating based on room number only
            installation_instance, created = Installation.objects.get_or_create(
                room=room_instance.room, # Ensure this matches the field type (e.g. room number if integer)
                defaults={'prework': "NO", 'product_arrived_at_floor':"NO", 'retouching':"NO", 'post_work':"NO"}
            )
            if created:
                logger.info(f"Created new Installation record for room {room_instance.room}")
        
        # Process main installation steps
        main_steps_map = {
            0: ('prework', 'prework_check_on', 'prework_checked_by'),
            1: ('product_arrived_at_floor', 'product_arrived_at_floor_check_on', 'product_arrived_at_floor_checked_by'),
            12: ('retouching', 'retouching_check_on', 'retouching_checked_by'),
            13: ('post_work', 'post_work_check_on', 'post_work_checked_by'),
        }

        for step_id_int, fields in main_steps_map.items():
            status_attr, date_attr, user_attr = fields
            checkbox_key = f"step_installation_{step_id_int}"
            form_date_key = f"date_installation_{step_id_int}"
            form_user_key = f"checked_by_installation_{step_id_int}"

            old_status_val = getattr(installation_instance, status_attr) == "YES"
            old_date_val = getattr(installation_instance, date_attr)
            old_user_val = getattr(installation_instance, user_attr)

            is_checked_in_form = request_post_data.get(checkbox_key) == "on"
            form_date_str = request_post_data.get(form_date_key)
            form_user_name = request_post_data.get(form_user_key, "").strip()

            if is_checked_in_form:
                setattr(installation_instance, status_attr, "YES")
                
                parsed_form_date = parse_date(form_date_str)
                if parsed_form_date:
                    setattr(installation_instance, date_attr, parsed_form_date)
                elif not old_status_val: # Newly checked and no specific date in form
                    setattr(installation_instance, date_attr, now().date())
                else: # Was already checked, form date field empty/invalid, preserve old
                    setattr(installation_instance, date_attr, old_date_val)

                # User assignment for checked item
                if not old_status_val: # Newly checked
                    setattr(installation_instance, user_attr, user_instance)
                else: # Was already checked
                    if form_user_name == user_instance.name: # JS set to current user, or admin typed their name
                        setattr(installation_instance, user_attr, user_instance)
                    elif not form_user_name and old_user_val: # User field cleared for already checked item
                        setattr(installation_instance, user_attr, old_user_val) # Preserve old user
                    elif old_user_val and form_user_name == old_user_val.name: # Name in form matches old user
                        setattr(installation_instance, user_attr, old_user_val) # Preserve old user
                    elif form_user_name: # Admin typed some other name or JS populated it (and it's not old user)
                        # Default to current user if form has a name not matching old user, 
                        # implying interaction or JS update.
                        setattr(installation_instance, user_attr, user_instance)
                    else: # Fallback, preserve old user if form name is empty and didn't match current user above
                         setattr(installation_instance, user_attr, old_user_val)
            else: # Not checked in form
                setattr(installation_instance, status_attr, "NO")
                setattr(installation_instance, date_attr, None)
                setattr(installation_instance, user_attr, None)
        
        installation_instance.save() # Save main installation steps

        # Process InstallDetail items
        for key in request_post_data:
            if key.startswith("step_detail_"):
                try:
                    step_id_str = key.split("_")[2]
                    form_date_key = f"date_detail_{step_id_str}"
                    form_user_key = f"checked_by_detail_{step_id_str}"

                    is_checked_in_form = request_post_data.get(key) == "on"
                    form_date_str = request_post_data.get(form_date_key)
                    form_user_name = request_post_data.get(form_user_key, "").strip()
                    
                    install_detail_item = None
                    created_new_detail = False

                    if step_id_str.startswith("newproduct_"):
                        if not is_checked_in_form: continue

                        product_id_for_new = int(step_id_str.split("_")[1])
                        product_instance = get_object_or_404(ProductData, id=product_id_for_new)
                        room_model_instance = room_instance.room_model_id
                        print('instance .........',product_instance.item)
                        install_detail_item, created = InstallDetail.objects.get_or_create(
                            installation=installation_instance,
                            product_id=product_instance,
                            room_id=room_instance,
                            defaults={
                                'room_model_id': room_model_instance,
                                'product_name': product_instance.description or product_instance.item,
                                'status': "YES",
                                'installed_on': parse_date(form_date_str) or now().date(),
                                'installed_by': user_instance
                            }
                        )
                        created_new_detail = created
                        if not created: # Already existed, treat as normal update path below
                            pass 
                        else: # Newly created and defaults set, skip further processing for this item in this loop iteration
                            continue # Already saved with correct initial values

                    else: # Existing InstallDetail item
                        detail_pk = int(step_id_str)
                        install_detail_item = get_object_or_404(InstallDetail, pk=detail_pk)
                        if install_detail_item.installation_id != installation_instance.id:
                            logger.warning(f"Data mismatch: InstallDetail {detail_pk}...")
                            continue
                    
                    # Common logic for existing or just-fetched-not-newly-created items
                    old_status_val = install_detail_item.status == "YES"
                    old_date_val = install_detail_item.installed_on
                    old_user_val = install_detail_item.installed_by

                    if is_checked_in_form:
                        install_detail_item.status = "YES"
                        parsed_form_date = parse_date(form_date_str)
                        if parsed_form_date:
                            install_detail_item.installed_on = parsed_form_date
                        elif not old_status_val: # Newly checked and no date in form
                            install_detail_item.installed_on = now().date()
                        else: # Was already checked, form date field empty/invalid
                            install_detail_item.installed_on = old_date_val
                        
                        # User assignment for checked detail item
                        if not old_status_val: # Newly checked
                            install_detail_item.installed_by = user_instance
                        else: # Was already checked
                            if form_user_name == user_instance.name:
                                install_detail_item.installed_by = user_instance
                            elif not form_user_name and old_user_val:
                                install_detail_item.installed_by = old_user_val
                            elif old_user_val and form_user_name == old_user_val.name:
                                install_detail_item.installed_by = old_user_val
                            elif form_user_name: # Admin typed some other name or JS populated it
                                install_detail_item.installed_by = user_instance # Default to current saver
                            else:
                                install_detail_item.installed_by = old_user_val
                    else: # Not checked in form
                        install_detail_item.status = "NO"
                        install_detail_item.installed_on = None
                        install_detail_item.installed_by = None
                    
                    install_detail_item.save()
                        
                except InstallDetail.DoesNotExist:
                    logger.error(f"InstallDetail with ID {step_id_str} not found...")

        # --- Automatic setting of day_install_began, install status, and day_install_complete ---
        installation_data_changed_by_automation = False

        # 1. Automatic setting of day_install_began
        # This relies on installation_instance.prework and installation_instance.prework_check_on
        # having been updated earlier in this function from the form data.
        if installation_instance.prework == "YES" and installation_instance.prework_check_on:
            # prework_check_on is DateTimeField, day_install_began is DateTimeField
            if installation_instance.day_install_began != installation_instance.prework_check_on:
                installation_instance.day_install_began = installation_instance.prework_check_on
                installation_data_changed_by_automation = True
        elif installation_instance.prework == "NO": # If prework is not YES or becomes NO
            if installation_instance.day_install_began is not None:
                installation_instance.day_install_began = None
                installation_data_changed_by_automation = True
        
        # 2. Automatic setting of install status and day_install_complete
        all_details_for_install = InstallDetail.objects.filter(installation=installation_instance)
        all_required_details_completed = False # Default to false
        latest_detail_completion_date = None

        if all_details_for_install.exists():
            all_required_details_completed = True # Assume true until a non-completed item is found
            for detail in all_details_for_install:
                if detail.status != "YES":
                    all_required_details_completed = False
                    latest_detail_completion_date = None # Reset if any item is not complete
                    break
                if detail.installed_on: # This is DateTimeField
                    if latest_detail_completion_date is None or detail.installed_on > latest_detail_completion_date:
                        latest_detail_completion_date = detail.installed_on
            if not all_required_details_completed: # if loop broke, ensure latest_date is None
                 latest_detail_completion_date = None
        else:
            # No InstallDetail items found for this installation.
            # "when all the dynamic products are marked done" - if no products, this condition is not met for "YES".
            all_required_details_completed = False 
            latest_detail_completion_date = None


        current_install_status = installation_instance.install
        current_install_complete_date = installation_instance.day_install_complete

        if all_required_details_completed and latest_detail_completion_date:
            # All details are completed and there's a valid completion date.
            if current_install_status != "YES":
                installation_instance.install = "YES"
                installation_data_changed_by_automation = True
            if current_install_complete_date != latest_detail_completion_date:
                installation_instance.day_install_complete = latest_detail_completion_date
                installation_data_changed_by_automation = True
        else: 
            # Not all details completed, or no details exist, or no latest completion date found (e.g. all products 'YES' but no dates)
            if current_install_status == "YES": # Only change if it was "YES"
                installation_instance.install = "NO" 
                installation_data_changed_by_automation = True
            if current_install_complete_date is not None:
                installation_instance.day_install_complete = None
                installation_data_changed_by_automation = True
        
        if installation_data_changed_by_automation:
            installation_instance.save()
            logger.info(f"Installation {installation_instance.id} updated by automation: day_install_began, install, day_install_complete.")

        return {"success": True, "message": "Installation data saved successfully!"}

    except Installation.DoesNotExist:
        return {"success": False, "message": "Installation record not found."}
    except RoomData.DoesNotExist:
         return {"success": False, "message": f"Room {room_number_str} not found."}
    except Exception as e:
        logger.error(f"Error in _save_installation_data for room {room_number_str}, install_id {installation_id_str}: {e}", exc_info=True)
        return {"success": False, "message": f"An unexpected error occurred: {str(e)}"}


@session_login_required
def installation_form(request):
    if not request.session.get("user_id"): # Redundant due to decorator, but good practice
        messages.warning(request, "You must be logged in to access the form.")
        return redirect("user_login")
    

    invited_user_id = request.session.get("user_id")
    invited_user_instance = get_object_or_404(InvitedUser, id=invited_user_id)
    checked_product_ids = []

    for key, value in request.POST.items():
        if key.startswith("step_detail_") and value == "on":
            detail_id = key.split("step_detail_")[1]
            product_id = request.POST.get(f"product_id_detail_{detail_id}")
            if product_id:
                checked_product_ids.append(product_id)

    # Now checked_product_ids contains ONLY product IDs that were ticked
    print("Checked Product IDs:", checked_product_ids)
    for product_id in checked_product_ids:
        try:
            inventory_item = Inventory.objects.get(item=product_id)
            inventory_item.quantity_installed += 1
            inventory_item.save()
        except Inventory.DoesNotExist:
            print(f"Inventory item with product_id {product_id} does not exist.")

    # Now use product_id, step_checked, etc.

    if request.method == "POST":
        room_number_str = request.POST.get("room_number")
        # For frontend, installation_id might not be explicitly in POST if it's a new installation.
        # The _save_installation_data helper will handle get_or_create for Installation.
        # If the form *does* pass an installation_id (e.g., from a hidden field after initial GET), it could be used.
        # For now, relying on room_number for get_or_create logic in the helper for frontend.
        
        result = _save_installation_data(request.POST, invited_user_instance, room_number_str)

        if result["success"]:
            messages.success(request, result["message"])
        else:
            messages.error(request, result["message"])
        return redirect("installation_form") # Redirect back to the form page

    # For GET request, the existing JS will call get_room_type to populate the form.
    return render(request, "installation_form.html", {
        "invited_user": invited_user_instance, # Used by JS to prefill user name
    })

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
            ship_date_str = request.POST.get("ship_date")
            expected_arrival_date_str = request.POST.get("expected_arrival_date")
            if ship_date_str:
                ship_date = make_aware(datetime.strptime(ship_date_str, "%Y-%m-%d"))

            if expected_arrival_date_str:
                expected_arrival_date = make_aware(datetime.strptime(expected_arrival_date_str, "%Y-%m-%d"))

            qty_shipped = int(request.POST.get("qty_shipped") or 0)
            supplier = request.POST.get("supplier")
            tracking_info = request.POST.get("tracking_info")
            
            print("expected_arrival_date ::", expected_arrival_date )
            print("ship_date ::", ship_date)
            print("qty_shipped ::", qty_shipped)
            print("supplier ::", supplier)
            print("tracking_info ::", tracking_info)
            print("user ::", user)
            print("client_item ::", client_item)
            # Save the shipping entry
            Shipping.objects.create(
                client_id=client_item,
                item=client_item,
                ship_date=ship_date,
                ship_qty=qty_shipped,
                supplier=supplier,
                bol=tracking_info,
                checked_by=user,
                expected_arrival_date = expected_arrival_date
            )
            print("Shipping ::", Shipping.objects.all())

            # Update Inventory
            inventory = Inventory.objects.filter(
                client_id__iexact=client_item,
                item__iexact=client_item
            ).first()            
            print("inventory ::", inventory)
            if inventory:
                print(f"Before update: qty_ordered = {inventory.qty_ordered}")
                inventory.qty_ordered = (inventory.qty_ordered or 0) + qty_shipped
                inventory.save()
                print(f"After update: qty_ordered = {inventory.qty_ordered}")

                messages.success(request, "Shipment submitted and inventory updated!")
            return redirect("inventory_shipment")

        except Exception as e:
            print("error ::", e)
            messages.error(request, f"Error submitting shipment: {str(e)}")

    return render(request, "inventory_shipment.html", {"user_name": user_name})

@session_login_required
def get_product_item_num(request):
    clientId = request.GET.get("room_number")
    try:
        client_data_fetched = ProductData.objects.get(client_id__iexact=clientId)
        get_item = client_data_fetched.item if client_data_fetched.item else ""
        supplier = client_data_fetched.supplier if client_data_fetched.supplier else "N.A."
        product_name = ProductData.objects.filter(item=client_data_fetched.item).values_list('description', flat=True).first() or ""
        return JsonResponse({"success": True, "room_type": get_item, "supplier": supplier, "product_name": product_name})
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
            received_date = request.POST.get("received_date")
            received_qty = int(request.POST.get("received_qty") or 0)
            damaged_qty = int(request.POST.get("damaged_qty") or 0)
            
            InventoryReceived.objects.create(
                client_id=client_item,
                item=client_item,
                received_date=received_date,
                received_qty=received_qty,
                damaged_qty=damaged_qty,
                checked_by=user
            )

            # Update Inventory
            inventory = Inventory.objects.filter(
                client_id__iexact=client_item,
                item__iexact=client_item
            ).first()
            if inventory:
                inventory.qty_received = (inventory.qty_received or 0) + (received_qty - damaged_qty)
                inventory.quantity_available = (inventory.quantity_available or 0) + (received_qty - damaged_qty)
                inventory.save()

            messages.success(request, "Inventory received successfully!")
            return redirect("inventory_received")

        except Exception as e:
            print("error ::", e)
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
        product_name = ProductData.objects.filter(item=client_data_fetched.item).values_list('description', flat=True).first() or ""
        return JsonResponse({"success": True, "product_item": get_item, "product_name": product_name})
    except RoomData.DoesNotExist:
        return JsonResponse({"success": False})


@login_required
def save_schedule(request):
    if request.method == "POST":
        post_data = request.POST
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

@session_login_required # Corrected decorator
def issue_list(request):
    user = get_object_or_404(InvitedUser, id=request.session.get("user_id"))
    user_roles = user.role
    queryset = Issue.objects.filter(
        Q(created_by=user) |
        Q(observers=user) |
        Q(assignee=user)
    ).distinct().order_by('-created_at').select_related('created_by', 'assignee')

    # Filtering
    status = request.GET.get('status')
    if status:
        queryset = queryset.filter(status=status)
    issue_type = request.GET.get('type')
    if issue_type:
        queryset = queryset.filter(type=issue_type)
    q = request.GET.get('q')
    if q:
        queryset = queryset.filter(Q(title__icontains=q) | Q(id__icontains=q))

    # Pagination
    paginator = Paginator(queryset, 10)  # Show 10 issues per page
    page_number = request.GET.get('page')
    try:
        issues_page = paginator.page(page_number)
    except PageNotAnInteger:
        issues_page = paginator.page(1)
    except EmptyPage:
        issues_page = paginator.page(paginator.num_pages)

    # For filter dropdowns
    issue_statuses = Issue.IssueStatus.choices if hasattr(Issue, 'IssueStatus') else [
        ('OPEN', 'Open'), ('WORKING', 'Working'), ('PENDING', 'Pending'), ('CLOSE', 'Close')
    ]
    issue_types = Issue.IssueType.choices if hasattr(Issue, 'IssueType') else [
        ('ROOM', 'Room'), ('FLOOR', 'Floor'),('OTHER', 'other')
    ]

    context = {
        'issues': issues_page,
        'user_roles': user_roles,
        'is_paginated': issues_page.has_other_pages(),
        'page_obj': issues_page,
        'issue_statuses': issue_statuses,
        'issue_types': issue_types,
    }
    return render(request, 'issues/issue_list.html', context)


@session_login_required  # or your login decorator
def issue_detail(request, issue_id):
    issue = get_object_or_404(Issue, id=issue_id)
    comments = issue.comments.all().select_related('content_type')
    invited_user = get_object_or_404(InvitedUser, id=request.session.get("user_id"))

    # Build comment_data for the template
    comment_data = []
    for comment in comments:
        commenter = comment.commenter
        comment_data.append({
            "comment_id": comment.id,
            "text_content": comment.text_content,
            "media": comment.media,
            "commenter_id": getattr(commenter, "id", None),
            "commenter_name": str(commenter),
            "is_by_current_user": commenter == invited_user,
            "created_at": comment.created_at,
        })

    can_comment = (
        issue.created_by == invited_user or
        invited_user in issue.observers.all() or
        issue.assignee == invited_user
    )

    comment_form = CommentForm()

    context = {
        'issue': issue,
        'comment_data': comment_data,
        'comment_form': comment_form,
        'user': invited_user,
        'can_comment': can_comment,
        'user_roles': request.session.get('user_roles', [])
    }
    return render(request, 'issues/issue_detail.html', context)
# ... (keep issue_create, invited_user_comment_create, and other non-admin views) ...

@session_login_required
def issue_create(request):
    user = get_object_or_404(InvitedUser, id=request.session.get("user_id"))
    
    initial_data = {}
    if request.method == 'GET':
        prefill_type = request.GET.get('type')
        prefill_room_id = request.GET.get('related_rooms')
        prefill_floor = request.GET.get('related_floors')
        prefill_product_id = request.GET.get('related_product')

        if prefill_type:
            initial_data['type'] = prefill_type
            
            if prefill_type == IssueType.ROOM and prefill_room_id:
                try:
                    room_ids = [int(id) for id in prefill_room_id.split(',')]
                    if RoomData.objects.filter(pk__in=room_ids).exists():
                        initial_data['related_rooms'] = room_ids
                except (ValueError, TypeError):
                    pass
            elif prefill_type == IssueType.FLOOR and prefill_floor:
                try:
                    floor_ids = [int(id) for id in prefill_floor.split(',')]
                    initial_data['related_floors'] = floor_ids
                except (ValueError, TypeError):
                    pass
            elif prefill_type == IssueType.PRODUCT and prefill_product_id:
                try:
                    product_ids = [int(id) for id in prefill_product_id.split(',')]
                    if ProductData.objects.filter(pk__in=product_ids).exists():
                        initial_data['related_product'] = product_ids
                except (ValueError, TypeError):
                    pass

    if request.method == 'POST':
        form = IssueForm(request.POST, request.FILES)
        
        if form.is_valid():
            issue = form.save(commit=False)
            issue.created_by = user
            
            # Convert floor IDs to integers before saving
            if issue.type == IssueType.FLOOR:
                floor_ids = form.cleaned_data.get('related_floors', [])
                issue.related_floors = [int(floor_id) for floor_id in floor_ids]
            
            issue.save()
            form.save_m2m()  # Save M2M relationships
            
            # Add creator as observer
            issue.observers.add(user)

            # Process media files
            media_urls = []
            images = form.cleaned_data.get('images', [])
            video = form.cleaned_data.get('video')

            for image in images:
                file_name = default_storage.save(f"issues/images/{uuid.uuid4()}_{image.name}", image)
                file_url = default_storage.url(file_name)
                media_urls.append({
                    'type': 'image',
                    'url': file_url,
                    'size': image.size,
                    'name': image.name
                })

            if video:
                file_name = default_storage.save(f"issues/videos/{uuid.uuid4()}_{video.name}", video)
                file_url = default_storage.url(file_name)
                media_urls.append({
                    'type': 'video',
                    'url': file_url,
                    'size': video.size,
                    'name': video.name
                })

            # Create initial comment if there's media
            if media_urls:
                Comment.objects.create(
                    issue=issue,
                    commenter=user,
                    text_content=form.cleaned_data.get('description', ''),
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
                    'errors': json.loads(form.errors.as_json())
                }, status=400)
            else:
                messages.error(request, error_message)
                return render(request, 'issues/issue_form.html', {'form': form})
    else:
        form = IssueForm(initial=initial_data)

    return render(request, 'issues/issue_form.html', {'form': form})

@session_login_required # Uses custom session auth
def invited_user_comment_create(request, issue_id):
    invited_user = get_object_or_404(InvitedUser, id=request.session.get("user_id"))
    issue = get_object_or_404(Issue, id=issue_id)

    # Permission check: User must be creator, observer, or assignee to comment
    can_comment = (
        issue.created_by == invited_user or
        invited_user in issue.observers.all() or
        issue.assignee == invited_user
    )

    if not can_comment:
        messages.error(request, "You do not have permission to comment on this issue.")
        return redirect('issue_detail', issue_id=issue.id)

    if request.method == 'POST':
        form = CommentForm(request.POST, request.FILES)
        if form.is_valid():
            comment = form.save(commit=False)
            comment.commenter = invited_user # Assign the InvitedUser instance
            comment.issue = issue

            media_info = []
            images = form.cleaned_data.get('images', [])
            video = form.cleaned_data.get('video')

            for img in images:
                if img.size > 4 * 1024 * 1024: # 4MB
                    messages.error(request, f"Image '{img.name}' exceeds 4MB limit.")
                    continue # Skip this file
                file_name = default_storage.save(f"issues/comments/user/{issue.id}/{uuid.uuid4()}_{img.name}", img)
                media_info.append({"type": "image", "url": default_storage.url(file_name), "name": img.name, "size": img.size})
            
            if video:
                if video.size > 100 * 1024 * 1024: # 100MB
                    messages.error(request, f"Video '{video.name}' exceeds 100MB limit.")
                else:
                    file_name = default_storage.save(f"issues/comments/user/{issue.id}/{uuid.uuid4()}_{video.name}", video)
                    media_info.append({"type": "video", "url": default_storage.url(file_name), "name": video.name, "size": video.size})

            comment.media = media_info
            comment.save()
            messages.success(request, "Your comment has been added.")
            return redirect('issue_detail', issue_id=issue.id) # Redirect to standard issue detail
        else:
            messages.error(request, "There was an error with your comment. Please check the details.")

            comments = issue.comments.all().select_related('content_type')
            for c in comments: # Pre-fetch commenter
                _ = c.commenter
            return render(request, 'issues/issue_detail.html', {
                'issue': issue,
                'comments': comments,
                'comment_form': form, # Pass the invalid form back
                'user': request.user, # Or invited_user if more appropriate for template
                'can_comment': can_comment # Pass the permission status, which must be True to reach here
            })
    else:
        # GET request usually means the form is displayed on the issue_detail page
        return redirect('issue_detail', issue_id=issue.id)

@login_required
def get_room_products(request):
    room_number = request.GET.get('room_number')
    installation_id = request.GET.get('installation_id')

    if not room_number:
        return JsonResponse({'error': 'Room number is required'}, status=400)

    if not installation_id:
        return JsonResponse({'error': 'Installation ID is required'}, status=400)

    try:
        with connection.cursor() as cursor:
            # Step 1: Get room_id and room_model_id
            cursor.execute("""
                SELECT rd.id as room_id, rm.id as room_model_id
                FROM room_data rd
                LEFT JOIN room_model rm ON rd.room_model_id = rm.id
                WHERE rd.room = %s
            """, [room_number])

            room_data = cursor.fetchone()
            if not room_data:
                return JsonResponse({'error': 'Room not found'}, status=404)

            room_id, room_model_id = room_data

            if not room_model_id:
                return JsonResponse({'error': 'No room model found for this room'}, status=404)

            # Step 2: Check if install_detail has entries
            cursor.execute("""
                SELECT 
                    id.product_id as id,
                    pd.item as name,
                    pd.description,
                    id.status,
                    id.installed_on,
                    u.name as installed_by
                FROM install_detail id
                JOIN product_data pd ON id.product_id = pd.id
                LEFT JOIN invited_users u ON id.installed_by = u.id
                WHERE id.room_id = %s AND id.installation_id = %s
                ORDER BY pd.item
            """, [room_id, installation_id])

            install_entries = cursor.fetchall()
            columns = [col[0] for col in cursor.description]

            if install_entries:
                products = []
                for row in install_entries:
                    product = dict(zip(columns, row))
                    if product['installed_on']:
                        product['installed_on'] = product['installed_on'].strftime('%Y-%m-%d')
                    products.append(product)

                return JsonResponse({'success': True, 'source': 'install_detail', 'products': products})

            # Step 3: Fallback to dynamic room model-based product lookup
            cursor.execute("""
                SELECT 
                    pd.id,
                    pd.item as name,
                    pd.description,
                    prm.quantity,
                    COALESCE(id.status, 'NO') as status,
                    id.installed_on,
                    u.name as installed_by
                FROM product_room_model prm
                JOIN product_data pd ON prm.product_id = pd.id
                LEFT JOIN install_detail id ON pd.id = id.product_id
                                           AND id.installation_id = %s
                                           AND id.room_id = %s
                LEFT JOIN invited_users u ON id.installed_by = u.id
                WHERE prm.room_model_id = %s
                ORDER BY pd.item
            """, [installation_id, room_id, room_model_id])

            dynamic_products = []
            columns = [col[0] for col in cursor.description]

            for row in cursor.fetchall():
                product = dict(zip(columns, row))
                if product['installed_on']:
                    product['installed_on'] = product['installed_on'].strftime('%Y-%m-%d')
                dynamic_products.append(product)

            return JsonResponse({'success': True, 'source': 'room_model_fallback', 'products': dynamic_products})

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@login_required # Standard Django login for admin views
def admin_get_installation_details(request):
    if not request.user.is_authenticated or not request.user.is_staff: # Basic permission check
        return JsonResponse({"success": False, "message": "Unauthorized"}, status=403)

    installation_id_str = request.GET.get("installation_id")
    room_number_str = request.GET.get("room_number")

    # Determine current user's name for JS prefill
    current_user_name = request.user.username # Default to username
    # Check if the logged-in user is an instance of InvitedUser and has a 'name' attribute
    # This depends on your authentication setup for admins.
    # If admins are Django users, request.user.name might not exist unless custom user model.
    # If admins are InvitedUser and session is set up, request.user could be InvitedUser.
    if hasattr(request.user, 'name') and request.user.name and isinstance(request.user, InvitedUser):
        current_user_name = request.user.name
    elif hasattr(request.user, 'get_full_name') and request.user.get_full_name():
        current_user_name = request.user.get_full_name()


    if installation_id_str: #优先处理编辑模式 (Prioritize edit mode if installation_id is present)
        try:
            installation_id = int(installation_id_str)
            # Fetch the specific installation
            installation = get_object_or_404(Installation, id=installation_id)
            # Get room number from the installation record
            room_num_for_helper = str(installation.room)

            data = _get_installation_checklist_data(room_number=room_num_for_helper, installation_id=installation_id)
            if data["success"]:
                data["current_user_name"] = current_user_name
            return JsonResponse(data)
        except ValueError:
            return JsonResponse({"success": False, "message": "Invalid Installation ID format."}, status=400)
        # Installation.DoesNotExist is already handled by get_object_or_404
        except Exception as e:
            logger.error(f"Error in admin_get_installation_details (edit mode) for install_id {installation_id_str}: {e}", exc_info=True)
            return JsonResponse({"success": False, "message": f"An unexpected server error occurred: {str(e)}"}, status=500)

    elif room_number_str: # 如果没有 installation_id，但有 room_number，则为创建模式加载 (If no installation_id, but room_number is present, load for create mode)
        try:
            # Validate room_number can be converted to int for RoomData query if necessary,
            # _get_installation_checklist_data expects room_number as string but might do internal conversion.
            # For create mode, installation_id is None.
            data = _get_installation_checklist_data(room_number=room_number_str, installation_id=None)
            if data["success"]:
                data["current_user_name"] = current_user_name
            else:
                # If _get_installation_checklist_data itself returns success:False, pass its message
                return JsonResponse(data, status=400 if data.get("message") else 500)
            return JsonResponse(data)
        except RoomData.DoesNotExist: # Explicitly catch if _get_installation_checklist_data can't find room
             return JsonResponse({"success": False, "message": f"Room {room_number_str} not found. Cannot create installation checklist."}, status=404)
        except ValueError: # e.g. if room_number_str is not a valid int and RoomData.room is int
            return JsonResponse({"success": False, "message": "Invalid Room Number format provided."}, status=400)
        except Exception as e:
            logger.error(f"Error in admin_get_installation_details (create mode) for room {room_number_str}: {e}", exc_info=True)
            return JsonResponse({"success": False, "message": f"An unexpected server error occurred: {str(e)}"}, status=500)
    else:
        return JsonResponse({"success": False, "message": "Either Installation ID (for edit) or Room Number (for create) is required."}, status=400)

@login_required # Standard Django login for admin views
@csrf_exempt # If using AJAX POST from admin template that might not embed CSRF token in form data easily initially
def admin_save_installation_details(request):
    if not request.user.is_authenticated or not request.user.is_staff:
        return JsonResponse({"success": False, "message": "Unauthorized"}, status=403)

    if request.method == "POST":
        installation_id_str = request.POST.get("installation_id")
        
        if not installation_id_str:
            return JsonResponse({"success": False, "message": "Installation ID is required in POST data."}, status=400)

        try:
            installation_id = int(installation_id_str)
            # Fetch the installation to get the room number for the helper
            installation_instance = get_object_or_404(Installation, id=installation_id)
            room_number_str = str(installation_instance.room) # Get room number from the instance

            # Determine the user instance for 'checked_by' fields.
            # If your admins are regular Django Users:
            # admin_user_instance = request.user
            # If your admins are also InvitedUser instances and logged in via session:
            # For simplicity, let's assume if an admin is doing this, they are the 'user_instance'
            # This might need refinement based on how admin identity is passed or if it should be logged differently.
            
            # For now, let's try to find an InvitedUser that matches the logged-in Django admin user's email.
            # This is a common pattern if you have two user systems.
            # Or, if admins are *always* also InvitedUsers and logged in through the custom session:
            admin_user_as_invited_user = None
            if hasattr(request.user, 'email'): # Check if the Django user has an email
                 admin_user_as_invited_user = InvitedUser.objects.filter(email=request.user.email).first()

            if not admin_user_as_invited_user:
                 # Fallback or error if no matching InvitedUser.
                 # For now, as a simple approach, create a placeholder or use a default admin InvitedUser if one exists.
                 # This part depends on your user management strategy for admins.
                 # Let's assume for now the logged-in Django user *is* the one making changes.
                 # The _save_installation_data expects an InvitedUser instance.
                 # If your request.user *is* an InvitedUser due to middleware, this is simpler.
                 # Given the mix of @login_required and @session_login_required, this needs clarity.
                 # Assuming @login_required means a Django user.
                 # We need an InvitedUser to pass to the helper.
                 
                 # If session_login_required was used for admins, then:
                 # invited_user_id = request.session.get("user_id")
                 # user_instance_for_saving = get_object_or_404(InvitedUser, id=invited_user_id)

                 # If @login_required (Django auth) is used for admins:
                 # We need a way to map Django User to InvitedUser for the save helper.
                 # Simplest for now: if a field 'name' on Django User matches an InvitedUser.name or email.
                 # This is a placeholder for robust user mapping.
                # Default to first admin if any, or handle error
                # This is a TEMPORARY HACK - replace with proper admin user (InvitedUser) retrieval
                user_instance_for_saving = InvitedUser.objects.filter(role__contains=['admin']).first()
                if not user_instance_for_saving and InvitedUser.objects.exists(): # fallback to any user if no admin
                    user_instance_for_saving = InvitedUser.objects.first()
                elif not InvitedUser.objects.exists():
                     return JsonResponse({"success": False, "message": "Configuration error: No InvitedUser available to attribute changes."}, status=500)

                logger.warning(f"Admin save: Using fallback InvitedUser '{user_instance_for_saving.name}' for changes by Django user '{request.user.username}'. Review user mapping.")

            else: # Found a matching InvitedUser for the Django admin
                user_instance_for_saving = admin_user_as_invited_user


            result = _save_installation_data(request.POST, user_instance_for_saving, room_number_str, installation_id_str)
            
            if result["success"]:
                return JsonResponse(result)
            else:
                return JsonResponse(result, status=400) # Or 500 if server-side issue in helper

        except ValueError:
            return JsonResponse({"success": False, "message": "Invalid Installation ID format."}, status=400)
        except Installation.DoesNotExist:
            return JsonResponse({"success": False, "message": "Installation record not found to save against."}, status=404)
        except Exception as e:
            logger.error(f"Critical error in admin_save_installation_details for install_id {installation_id_str}: {e}", exc_info=True)
            return JsonResponse({"success": False, "message": f"An server error occurred: {str(e)}"}, status=500)

    return JsonResponse({"error": "Invalid request method. Only POST is allowed."}, status=405)
