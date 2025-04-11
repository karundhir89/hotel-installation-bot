import ast
import json
import random
import string
from datetime import date
from functools import wraps

import bcrypt
import environ
import requests
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.mail import send_mail
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.utils.timezone import now
from django.views.decorators.csrf import csrf_exempt
from hotel_bot_app.utils.prompts import (fetch_data_from_sql,
                                         format_gpt_prompt,
                                         generate_final_response,
                                         gpt_call_json_func,
                                         load_database_schema,
                                         verify_sql_query)
from openai import OpenAI

from .models import *
from .models import ChatSession

env = environ.Env()
environ.Env.read_env()

password_generated = "".join(random.choices(string.ascii_letters + string.digits, k=6))
open_ai_key = env("open_ai_api_key")

client = OpenAI(api_key=open_ai_key)


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


@csrf_exempt
def chatbot_api(request):
    if request.method == "POST":
        data = json.loads(request.body)
        user_message = data.get("message", "").strip()

        if not user_message:
            return JsonResponse({"response": "⚠️ No message sent."}, status=400)

        session_id = request.session.get("chat_session_id")
        print("session_idddd", session_id)
        if not session_id:
            session = ChatSession.objects.create()
            request.session["chat_session_id"] = session.id
            request.session.set_expiry(3600)  # Session expires in 1 hour (3600 seconds)
            session_id = session.id  # Update the local variable
            print("session_idddd", session_id)
        else:
            try:
                session = ChatSession.objects.get(id=session_id)
            except ChatSession.DoesNotExist:
                session = ChatSession.objects.create()
                request.session["chat_session_id"] = session.id
                request.session.set_expiry(3600)
                session_id = session.id

        ChatHistory.objects.create(session=session, message=user_message, role="user")

        try:
            DB_SCHEMA = load_database_schema()

            # Prompt GPT to generate SQL
            prompt_first = format_gpt_prompt(user_message, DB_SCHEMA)
            prompt_response = gpt_call_json_func(
                [{"role": "user", "content": prompt_first}],
                gpt_model="gpt-4o",
                json_required=True,
            )
            print("First GPT response:", prompt_response)

            sql_query = prompt_response.get("query")
            rows = None
            bot_message = None

            if sql_query:
                try:
                    # Try executing the query directly
                    rows = fetch_data_from_sql(sql_query)

                except Exception as db_error:
                    print("DB execution error:", db_error)

                    # Run GPT SQL verifier
                    verification = verify_sql_query(
                        user_message=user_message,
                        sql_query=sql_query,
                        prompt_data=DB_SCHEMA,
                        error_message=str(db_error),
                        gpt_model="gpt-4o"
                    )

                    print("Verification result:", verification)

                    # If GPT recommends a fixed query, retry with that
                    if not verification["is_valid"] and verification.get("recommendation"):
                        try:
                            rows = fetch_data_from_sql(verification["recommendation"])
                            sql_query = verification["recommendation"]
                        except Exception as second_error:
                            print("Retry failed:", second_error)
                            raise second_error  # Let it get caught below
                    else:
                        raise db_error  # Re-raise if no fix recommended

            bot_message = generate_final_response(user_message, rows)

            # Save assistant's response
            ChatHistory.objects.create(session=session, message=bot_message, role="assistant")

            return JsonResponse({"response": bot_message})

        except Exception as e:
            print("Error occurred:", e)
            error_message = f"Sorry, I couldn't process that due to: {str(e)}"
            ChatHistory.objects.create(session=session, message=error_message, role="assistant")
            return JsonResponse({"response": error_message})

    return JsonResponse({"error": "Invalid request"}, status=400)


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


def display_prompts(request):
    print(request)
    prompts = Prompt.objects.all()  # Fetch all records
    for prompt in prompts:
        print(prompt.id, prompt.prompt_number, prompt.description)
    return render(request, "edit_prompt.html", {"prompts": prompts})


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


def user_management(request):
    prompts = InvitedUser.objects.all()
    print("users", prompts)

    return render(request, "user_management.html", {"prompts": prompts})


def add_users_roles(request):
    print(request.POST)
    if request.method == "POST":
        name = request.POST.get("name")  # Get the ID
        email = request.POST.get("email")  # Get the new description
        roles = request.POST.get("role")  # Get the new description
        status = request.POST.get("status")  # Get the new description
        roles_list = roles.split(", ") if roles else []
        print(name, email, type(roles_list), roles_list, status, password_generated)

        user = InvitedUser.objects.create(
            name=name,
            role=roles_list,
            last_login=now(),
            email=email,
            password=bcrypt.hashpw(password_generated.encode(), bcrypt.gensalt()),
        )
        send_test_email(email, password_generated)

    return render(request, "add_users_roles.html")


def send_test_email(recipient_email, password):
    subject = "Your Access to Hotel Installation Admin"
    from_email = env("EMAIL_HOST_USER")
    recipient_list = [recipient_email]

    html_message = render_to_string(
        "email_sample.html", {"email": recipient_email, "password": password}
    )
    plain_message = strip_tags(html_message)

    send_mail(
        subject,
        plain_message,
        from_email,
        recipient_list,
        html_message=html_message,
        fail_silently=False,
    )


def user_login(request):
    # Redirect to dashboard if already logged in
    if request.session.get("user_id"):
        return redirect("/dashboard")

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
    # Fetch room data from the database
    rooms = RoomData.objects.all()

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
    install = Installation.objects.all()
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


def get_room_type(request):
    room_number = request.GET.get("room_number")
    installed_by = request.GET.get("installed_by", "unknown_user")
    installed_on = date.today()

    try:
        room_data = RoomData.objects.get(room=room_number)
        room_type = room_data.room_model or ""
        room_model = RoomModel.objects.get(room_model=room_type)
        room_model_id = room_model.id

        print("............", room_model_id)
        product_room_models = ProductRoomModel.objects.filter(
            room_model_id=room_model_id
        )

        # Check if InstallDetail already exists
        existing_installs = InstallDetail.objects.filter(room_id=room_data)

        if existing_installs.exists():
            saved_items = [
                {
                    "install_id": inst.install_id,
                    "product_id": inst.product_id.id if inst.product_id else None,
                    "product_name": inst.product_name,
                    "room_id": inst.room_id.id if inst.room_id else None,
                    "room_model_id": (
                        inst.room_model_id.id if inst.room_model_id else None
                    ),
                    "installed_by": (
                        inst.installed_by.name if inst.installed_by else None
                    ),
                    "installed_on": str(inst.installed_on),
                    "status": inst.status,
                }
                for inst in existing_installs
            ]
        else:
            # Create new InstallDetails from ProductRoomModel
            saved_items = []
            for prm in product_room_models:
                install = InstallDetail.objects.create(
                    product_id=prm.product_id,
                    room_id=room_data,
                    room_model_id=room_model,
                    product_name=prm.product_id.description,
                    installed_on=installed_on,
                )

                saved_items.append(
                    {
                        "install_id": install.install_id,
                        "product_id": (
                            install.product_id.id if install.product_id else None
                        ),
                        "product_name": install.product_name,
                        "room_id": install.room_id.id if install.room_id else None,
                        "room_model_id": (
                            install.room_model_id.id if install.room_model_id else None
                        ),
                        "installed_by": (
                            install.installed_by.name if install.installed_by else None
                        ),
                        "installed_on": str(install.installed_on),
                        "status": install.status,
                    }
                )

        # Default check items
        check_items = [
            {"id": 0, "label": "Pre-Work completed."},
            {"id": 1, "label": "The product arrived at the floor."},
            {"id": 12, "label": "Retouching."},
            {"id": 13, "label": "Post Work."},
        ]

        # Add dynamic check items from ProductRoomModel
        for prm in product_room_models:
            if prm.product_id and prm.product_id.description:
                check_items.append(
                    {
                        "id": prm.id,
                        "label": f"{prm.product_id.description} (Qty: {prm.quantity})",
                    }
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
def installation_form(request):
    if not request.session.get("user_id"):
        messages.warning(request, "You must be logged in to access the form.")
        return redirect("user_login")

    return render(request, "installation_form.html")


def inventory_shipment(request):
    return render(request, "inventory_shipment.html")


def get_product_item_num(request):
    clientId = request.GET.get("room_number")
    try:
        print("Seminole", clientId, "hiii")
        client_data_fetched = ProductData.objects.get(client_id=clientId)
        print(client_data_fetched)
        get_item = client_data_fetched.item if client_data_fetched.item else ""
        print("Seminole grand", get_item)
        return JsonResponse({"success": True, "room_type": get_item})
    except RoomData.DoesNotExist:
        return JsonResponse({"success": False})


def inventory_received(request):
    user_id = request.session.get("user_id")
    user_name = ""

    if user_id:
        try:
            user = InvitedUser.objects.get(id=user_id)
            user_name = user.name  # Adjust field name if different
        except InvitedUser.DoesNotExist:
            pass

    return render(request, "inventory_received.html", {"user_name": user_name})


def inventory_pull(request):
    user_id = request.session.get("user_id")
    user_name = ""

    if user_id:
        try:
            user = InvitedUser.objects.get(id=user_id)
            user_name = user.name  # Adjust field name if different
        except InvitedUser.DoesNotExist:
            pass

    return render(request, "inventory_pull.html", {"user_name": user_name})


def inventory_pull_item(request):
    clientId = request.GET.get("room_number")
    try:
        print("lllll", clientId, "hiii")
        client_data_fetched = ProductData.objects.get(client_id=clientId)
        print(client_data_fetched)
        get_item = client_data_fetched.item if client_data_fetched.item else ""
        print("grand", get_item)
        return JsonResponse({"success": True, "room_type": get_item})
    except RoomData.DoesNotExist:
        return JsonResponse({"success": False})


def inventory_received_item_num(request):
    clientId = request.GET.get("room_number")
    try:
        print("lllll", clientId, "hiii")
        user_id = request.session.get("user_id")
        client_data_fetched = ProductData.objects.get(client_id=clientId)
        print(client_data_fetched)
        get_item = client_data_fetched.item if client_data_fetched.item else ""
        print("grand", get_item)
        return JsonResponse({"success": True, "room_type": get_item})
    except RoomData.DoesNotExist:
        return JsonResponse({"success": False})


@login_required
def save_installation(request):
    if request.method == "POST":
        installation_id = request.POST.get("installation_id")
        print("[hello]", installation_id)
        room = request.POST.get("room", "").strip()
        product_available = request.POST.get("product_available", "").strip()
        prework = request.POST.get("prework", "").strip()
        install = request.POST.get("install", "").strip()
        post_work = request.POST.get("post_work", "").strip()
        day_install_began = request.POST.get("day_install_began", "").strip()
        day_instal_complete = request.POST.get("day_instal_complete", "").strip()

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
                installation.day_install_began = day_install_began
                installation.day_instal_complete = day_instal_complete
                installation.save()
            else:
                print("Adding new row")
                Installation.objects.create(
                    room=room,
                    product_available=product_available,
                    prework=prework,
                    install=install,
                    post_work=post_work,
                    day_install_began=day_install_began,
                    day_instal_complete=day_instal_complete,
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
                installation.production_starts = production_starts
                installation.production_ends = production_ends
                installation.shipping_depature = shipping_depature
                installation.shipping_arrival = shipping_arrival
                installation.custom_clearing_starts = custom_clearing_starts
                installation.custom_clearing_ends = custom_clearing_ends
                installation.arrive_on_site = arrive_on_site
                installation.pre_work_starts = pre_work_starts
                installation.pre_work_ends = pre_work_ends
                installation.install_starts = install_starts
                installation.install_ends = install_ends
                installation.post_work_starts = post_work_starts
                installation.post_work_ends = post_work_ends
                installation.floor_completed = floor_completed
                installation.floor_closes = floor_closes
                installation.floor_opens = floor_opens
                installation.save()
            else:
                print("under new")
                print(post_data)
                Schedule.objects.create(
                    phase=phase,
                    floor=floor,
                    production_starts=production_starts,
                    production_ends=production_ends,
                    shipping_depature=shipping_depature,
                    shipping_arrival=shipping_arrival,
                    custom_clearing_starts=custom_clearing_starts,
                    custom_clearing_ends=custom_clearing_ends,
                    arrive_on_site=arrive_on_site,
                    pre_work_starts=pre_work_starts,
                    pre_work_ends=pre_work_ends,
                    install_starts=install_starts,
                    install_ends=install_ends,
                    post_work_starts=post_work_starts,
                    post_work_ends=post_work_ends,
                    floor_completed=floor_completed,
                    floor_closes=floor_closes,
                    floor_opens=floor_opens,
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
        qty_ordered = post_data.get("qty_ordered") or 0
        price = post_data.get("price") or 0
        a = post_data.get("a") or 0
        a_col = post_data.get("a_col") or 0
        a_lo = post_data.get("a_lo") or 0
        a_lo_dr = post_data.get("a_lo_dr") or 0
        b = post_data.get("b") or 0
        c_pn = post_data.get("c_pn") or 0
        c = post_data.get("c") or 0
        curva_24 = post_data.get("curva_24") or 0
        curva = post_data.get("curva") or 0
        curva_dis = post_data.get("curva_dis") or 0
        d = post_data.get("d") or 0
        dlx = post_data.get("dlx") or 0
        presidential_suite = post_data.get("presidential_suite") or 0
        st_c = post_data.get("st_c") or 0
        suite_a = post_data.get("suite_a") or 0
        suite_b = post_data.get("suite_b") or 0
        suite_c = post_data.get("suite_c") or 0
        suite_mini = post_data.get("suite_mini") or 0
        curva_35 = post_data.get("curva_35") or 0
        client_selected = post_data.get("client_selected") or 0
        try:
            if product_id:
                print("inside")
                installation = ProductData.objects.get(id=product_id)
                installation.product_id = product_id
                installation.item = item
                installation.client_id = client_id
                installation.description = description
                installation.qty_ordered = qty_ordered
                installation.price = price
                installation.a = a
                installation.a_col = a_col
                installation.a_lo = a_lo
                installation.a_lo_dr = a_lo_dr
                installation.b = b
                installation.c_pn = c_pn
                installation.c = c
                installation.curva_24 = curva_24
                installation.curva = curva
                installation.curva_dis = curva_dis
                installation.d = d
                installation.dlx = dlx
                installation.presidential_suite = presidential_suite
                installation.st_c = st_c
                installation.suite_a = suite_a
                installation.suite_b = suite_b
                installation.suite_c = suite_c
                installation.suite_mini = suite_mini
                installation.curva_35 = curva_35
                installation.client_selected = client_selected

                installation.save()
            else:
                print("Adding new row")
                ProductData.objects.create(
                    item=item,
                    client_id=client_id,
                    description=description,
                    qty_ordered=qty_ordered,
                    price=price,
                    a=a,
                    a_col=a_col,
                    a_lo=a_lo,
                    a_lo_dr=a_lo_dr,
                    b=b,
                    c_pn=c_pn,
                    c=c,
                    curva_24=curva_24,
                    curva=curva,
                    curva_dis=curva_dis,
                    d=d,
                    dlx=dlx,
                    presidential_suite=presidential_suite,
                    st_c=st_c,
                    suite_a=suite_a,
                    suite_b=suite_b,
                    suite_c=suite_c,
                    suite_mini=suite_mini,
                    curva_35=curva_35,
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
def dashboard(request):
    user_id = request.session.get("user_id")

    if not user_id:
        return redirect("user_login")

    try:
        user = InvitedUser.objects.get(id=user_id)

        # If user.role is already a list (e.g., from a JSONField or ArrayField)
        user_roles = [
            role.strip().lower() for role in user.role if isinstance(role, str)
        ]

        return render(
            request, "dashboard.html", {"name": user.name, "roles": user_roles}
        )
    except InvitedUser.DoesNotExist:
        return redirect("user_login")


def installation_control_form(request):
    if request.method == "POST":
        try:
            client_item = request.POST.get("client_item")
            product_item = request.POST.get("product_item")
            ship_date = request.POST.get("ship_date")
            qty_shipped = request.POST.get("qty_shipped")
            supplier = request.POST.get("supplier")
            supplier_date = request.POST.get("supplier_date")
            tracking_info = request.POST.get("tracking_info")
            final_date = request.POST.get("final_date")
            final_by = request.POST.get("final_by")
            final_notes = request.POST.get("final_notes")

            # Create a new Shipping entry
            Shipping.objects.create(
                client_id=client_item,
                item=product_item,
                ship_date=ship_date,
                ship_qty=qty_shipped,
                supplier=supplier,
                supplier_date=supplier_date,
                bol=tracking_info,
                date=final_date,
                by=final_by,
                notes=final_notes,
            )

            messages.success(request, "Shipment submitted successfully!")
        except Exception as e:
            messages.error(request, f"Error submitting shipment: {str(e)}")

    # Pass your check_items context if needed
    return render(
        request,
        "inventory_shipment.html",
        {
            "check_items": [],  # Replace with actual data
        },
    )


from django.contrib import messages
from django.shortcuts import redirect, render


def inventory_pull_form(request):
    if request.method == "POST":
        try:
            user_id = request.session.get("user_id")
            print(request.POST)

            client_id = request.POST.get("client_id")
            item = request.POST.get("item_number")
            available_qty = request.POST.get("qty_available_ready_to_pull")
            is_pulled = request.POST.get("pull_checked") == "on"
            pulled_date = request.POST.get("pull_date_text")
            qty_pulled_for_install = request.POST.get("qty_pulled_for_install")
            pulled_by = user_id
            floor = request.POST.get("floor_where_going")
            qty_pulled = request.POST.get("inventory_available_after_pull")
            notes = request.POST.get("pull_notes")  # This line was incorrect before

            PullInventory.objects.create(
                client_id=client_id,
                item=item,
                available_qty=available_qty,
                is_pulled=is_pulled,
                pulled_date=pulled_date,
                qty_pulled_for_install=qty_pulled_for_install,
                pulled_by=pulled_by,
                floor=floor,
                qty_pulled=qty_pulled,
                notes=notes,
            )

            messages.success(request, "Inventory pull submitted successfully!")
        except Exception as e:
            print(f"Error submitting inventory pull: {str(e)}")
            messages.error(request, f"Error submitting inventory pull: {str(e)}")

        # 🔄 Prevent resubmission by redirecting after POST
        return redirect("inventory_pull_form")

    # For GET request
    return render(
        request,
        "inventory_pull.html",
        {
            "check_items": [],  # Replace or update as needed
        },
    )
