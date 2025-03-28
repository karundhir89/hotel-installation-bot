from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import json
from django.shortcuts import render
from openai import OpenAI
import requests
import bcrypt
import json
from .models import *
import ast
from .models import ChatSession
from django.shortcuts import get_object_or_404
from django.utils.timezone import now
import random
import string
from django.core.mail import send_mail
import environ
env = environ.Env()
environ.Env.read_env()

password_generated = ''.join(random.choices(string.ascii_letters + string.digits, k=6))
open_ai_key=env("open_ai_api_key")

client = OpenAI(api_key=open_ai_key)
from django.db import connection

def gpt_call_json_func(message,gpt_model,json_required=True,temperature=0):
	try:
		print("gpt function call")
		json_payload = {
			'model': gpt_model,
			'temperature': temperature,
			'messages': message
		}
		
		if json_required:
			json_payload['response_format'] = {"type": "json_object"}
		
		gpt_response = requests.post(
			'https://api.openai.com/v1/chat/completions',
			json=json_payload,
			headers={
				'Authorization': f'Bearer {open_ai_key}',
				'Content-Type': 'application/json'
			}
		)
		print("gpt response got is ",gpt_response.json())
		print("gpt function ended with ....",gpt_response.json()['choices'][0]['message']['content'])
		# print("gpt response got is ",gpt_response.json()['choices'])
		return gpt_response.json()['choices'][0]['message']['content']
	except Exception as e:
		print("gpt call error",e)
		return 'None'
    


def extract_values(json_obj, keys):
    """
    Extract values from a JSON object based on the provided list of keys.
    :param json_obj: Dictionary (parsed JSON object)
    :param keys: List of keys to extract values for
    :return: None (prints formatted output)
    """
    table_selected=''
    for key in keys:
        value = json_obj.get(key, None)
        table_selected+=f"Table name is '{key}' and column name is {value}\n\n"
    return table_selected



@csrf_exempt  # Disable CSRF for simplicity (not recommended for production)
def chatbot_api(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        user_message = data.get('message', '')

        # Retrieve or create chat session
        session_id = request.session.get("chat_session_id")

        if not session_id:
            session = ChatSession.objects.create()
            request.session["chat_session_id"] = session.id
        else:
            session = get_object_or_404(ChatSession, id=session_id)

        # Store user message in DB
        ChatHistory.objects.create(session=session, message=user_message, role="user")

        # Retrieve full chat history
        Table_identification = Prompt.objects.filter(prompt_number=1).values_list("description", flat=True).first()
        json_of_tables = Prompt.objects.filter(prompt_number=2).values_list("description", flat=True).first()
        
        json_of_tables=ast.literal_eval(json_of_tables)
        # GPT API Call
        response = gpt_call_json_func([
            {'role': 'system', 'content': Table_identification + '\n\n' + 'Here is my query\n' + user_message}
        ], gpt_model='gpt-4o')

        try:
            bot_response = ast.literal_eval(response)
            extracted_values = extract_values(json_of_tables, bot_response['data'])
            query_sql = json.loads(gpt_call_json_func([
                {'role': 'system', 'content': 'Generate an SQL query based on my query and return JSON with key "query".\n'
                 'Instructions: always use LOWER in WHERE condition.\n\n'
                 'User query:\n' + user_message + '\n\n'
                 'Table details:\n' + extracted_values}
            ], gpt_model='gpt-4o'))
            
            # Execute SQL query
            with connection.cursor() as cursor:
                cursor.execute(query_sql['query'])
                rows = cursor.fetchall()

            bot_message = f"The answer is {rows}"
        except Exception as e:
            print("Error processing bot response:", e)
            bot_message = "Sorry, I couldn't process that."

        # Store assistant message in DB
        ChatHistory.objects.create(session=session, message=bot_message, role="assistant")

        # Update chat history after bot response
        return JsonResponse({'response': bot_message})

    return JsonResponse({'error': 'Invalid request'}, status=400)

@csrf_exempt
def get_chat_history(request):
    session_id = request.session.get("chat_session_id")
    
    if not session_id:
        return JsonResponse({"chat_history": []})  # No session, return empty history

    session = get_object_or_404(ChatSession, id=session_id)
    history_messages = list(ChatHistory.objects.filter(session=session).values("role", "message"))

    return JsonResponse({"chat_history": history_messages})


def chatbot(request):
    return render(request, 'chatbot.html')

def display_prompts(request):
    print(request)
    prompts = Prompt.objects.all()  # Fetch all records
    for prompt in prompts:
        print(prompt.id, prompt.prompt_number, prompt.description)
    return render(request, 'edit_prompt.html', {'prompts': prompts}) 

def update_prompt(request):
    if request.method == "POST":
        prompt_id = request.POST.get("prompt_id")  # Get the ID
        prompt_description = request.POST.get("prompt_description")  # Get the new description
        
        try:
            prompt = Prompt.objects.get(id=prompt_id)  # Fetch the object
            prompt.description = prompt_description  # Update the description
            prompt.save()  # Save changes
            print("Updated successfully")
        except Prompt.DoesNotExist:
            print("Prompt not found")

    return render(request, 'edit_prompt.html')

def user_management(request):
    prompts = InvitedUser.objects.all() 
    print("users",prompts)
    
    return render(request, 'user_management.html',{'prompts': prompts})


def add_users_roles(request):
    print(request.POST)
    if request.method == "POST":
        name = request.POST.get("name")  # Get the ID
        email = request.POST.get("email")  # Get the new description
        roles = request.POST.get("role")  # Get the new description
        status = request.POST.get("status")  # Get the new description
        roles_list = roles.split(", ") if roles else []
        print(name,email,type(roles_list),roles_list,status,password_generated)

        user = InvitedUser.objects.create(name=name,role=roles_list,last_login=now(),email=email,
password=bcrypt.hashpw(password_generated.encode(), bcrypt.gensalt())
        )
        send_test_email(email,password_generated)
        
    return render(request, 'add_users_roles.html')


def send_test_email(recipient_email,password):
    subject = 'Test Email from Django'
    message = 'Hello, this is a test email sent using Django and SMTP'
    from_email = env('EMAIL_HOST_USER')  # This is the sender's email
    recipient_list = [recipient_email]  # Add the recipient's email address here
    
    send_mail(subject, message, from_email, recipient_list, fail_silently=False)

def user_login(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            username = data.get("email")
            entry_password = data.get("password")
            print(username,entry_password)
            
            if not username or not entry_password:
                return JsonResponse({"error": "Username and password are required."}, status=400)
            
            user = InvitedUser.objects.filter(email=username).values('email', 'password').first()
            
            if user is None:
                return JsonResponse({"error": "Email does not exist."}, status=404)
            print(user["password"])
            stored_hashed_password = bytes(user["password"])
            
            condition=bcrypt.checkpw(entry_password.encode(),stored_hashed_password)
            if condition:
                return JsonResponse({"message": "successful."}, status=200)
            
            return JsonResponse({"error": "Incorrect password."}, status=401)
        
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON data."}, status=400)
        except Exception as e:
            return JsonResponse({"error": f"An error occurred: {str(e)}"}, status=500)
    
    return render(request, 'user_login.html')
          
