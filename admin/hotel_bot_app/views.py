from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import json
from django.shortcuts import render, redirect
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
from django.contrib.auth.decorators import login_required
env = environ.Env()
environ.Env.read_env()

password_generated = ''.join(random.choices(string.ascii_letters + string.digits, k=6))
open_ai_key=env("open_ai_api_key")

client = OpenAI(api_key=open_ai_key)
from django.db import connection

def gpt_call_json_func(message,gpt_model,json_required=True,temperature=0):
	try:
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
    print("table selected ,,,,,,",table_selected)
    return table_selected



@csrf_exempt  # Disable CSRF for simplicity (not recommended for production)
def chatbot_api(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        user_message = data.get('message', '')

        # Retrieve or create chat session
        session_id = request.session.get("chat_session_id")
        print("session ID",session_id)
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
        word_spaces_prompt = Prompt.objects.filter(prompt_number=3).values_list("description", flat=True).first()
        user_query_identification_prompt = Prompt.objects.filter(prompt_number=4).values_list("description", flat=True).first()
        finalised_response_prompt = Prompt.objects.filter(prompt_number=5).values_list("description", flat=True).first()
        generate_sql_prompt = Prompt.objects.filter(prompt_number=6).values_list("description", flat=True).first()

        def fetch_data_from_sql(query):
        # Execute SQL query
            print("sql query :::::;",query)
            with connection.cursor() as cursor:
                cursor.execute(query)
                rows = cursor.fetchall()
                print("rows fetched .....",rows)
                return rows
        try:
            prompt_first = gpt_call_json_func([
                {'role': 'system', 'content': """You are a chatbot specialized in hotel furniture installation. Your task is to analyze the User Query and determine its intent.
 
If the user is engaging in general conversation (e.g., greetings like "hello" or "how are you?"), respond accordingly.
 
If the query relates to database columns, hotel-related topics, models, inventory, or installation (such as rooms, services, IDs, scheduling, or product details), extract and return the most relevant tables, columns, data and "suggested query logic" in JSON format to assist in building SQL queries later.
 
Otherwise, continue the conversation naturally.
 
Do not ask questions.
 
Available Tables & Schema:
 
Table: "room_data"
Columns: "id" [serial4], "room" [text], "floor" [text], "king" [text], "double" [text], "exec_king" [text], "bath_screen" [text], "room_model" [text], "left_desk" [text], "right_desk" [text], "to_be_renovated" [text], "descripton" [text]
Sample database rows:
                 
{{"room_data": [ {{ "id" : 1, "room" : "1607", "floor" : "16", "king" : "YES", "double" : "NO", "exec_king" : "NO", "bath_screen" : "YES", "room_model" : "B", "left_desk" : "YES", "right_desk" : "NO", "to_be_renovated" : "YES", "description" : "King,  medium desk, w screen, custom ceiling and closet wall covering" }}, {{ "id" : 2, "room" : "1609", "floor" : "16", "king" : "NO", "double" : "YES", "exec_king" : "NO", "bath_screen" : "YES", "room_model" : "A LO", "left_desk" : "YES", "right_desk" : "NO", "to_be_renovated" : "YES", "description" : "Double, Long desk, w screen, custom ceiling and closet wall covering" }}, {{ "id" : 3, "room" : "1611", "floor" : "16", "king" : "YES", "double" : "NO", "exec_king" : "NO", "bath_screen" : "YES", "room_model" : "A COL", "left_desk" : "YES", "right_desk" : "NO", "to_be_renovated" : "YES", "description" : "King, Long desk, w screen, custom ceiling and closet wall covering" }}, {{ "id" : 4, "room" : "1613", "floor" : "16", "king" : "NO", "double" : "YES", "exec_king" : "NO", "bath_screen" : "YES", "room_model" : "A", "left_desk" : "YES", "right_desk" : "NO", "to_be_renovated" : "NO", "description" : "Double, Long desk, w screen, custom ceiling and closet wall covering" }}]}}
 
Table: "room_model"
Columns: "id" [serial4], "room_model" [text], "total" [text]
Sample database rows:
{{"room_model": [{{"id" : 1,"room_model" : "A","total" : "31"}},{{"id" : 2,"room_model" : "A COL","total" : "72"}},{{"id" : 3,"room_model" : "A LO","total" : "36"}},{{"id" : 4,"room_model" : "A LO DR","total" : "3"}},]}}
 
 
Table: "product_data"
Columns: "id" [serial4], "item" [text], "client_id" [text], "description" [text], "qty_ordered" [text], "price" [text], "client_selected" [text]
Sample database rows:
{{"product_data": [{{"id" : 1,"item" : "KS-JWM-113","client_id" : "P125","description" : "Desk\/Dining Chair","qty_ordered" : "320","price" : "255.0","client_selected" : "1"}},{{"id" : 2,"item" : "KS-JWM-702A","client_id" : "P123","description" : "Custom Dining Chair","qty_ordered" : "176","price" : "296.82","client_selected" : "1"}},{{"id" : 3,"item" : "KS-JVM-715-SABC","client_id" : "P120","description" : "Sofa SUITE A, B, C","qty_ordered" : "9","price" : "1646.6615384615384","client_selected" : "1"}},{{"id" : 4,"item" : "KS-JVM-715-CURVADIS","client_id" : "P121","description" : "Sofa CURVA DIS","qty_ordered" : "2","price" : "1646.6615384615384","client_selected" : "1"}}]}}
 
 
Table: "inventory"
Columns: "id" [serial4], "item" [text], "client_id" [text], "qty_ordered" [text], "qty_received" [text], "quantity_installed" [text], "quantity_available" [text]
Sample database rows:
{{"inventory": [{{"id" : 1,"item" : "KS-JWM-113","client_id" : "P125","qty_ordered" : 320,"qty_received" : 0,"quantity_installed" : 0,"quantity_available" : 0}},{{"id" : 2,"item" : "KS-JWM-702A","client_id" : "P123","qty_ordered" : 176,"qty_received" : 0,"quantity_installed" : 0,"quantity_available" : 0}},{{"id" : 3,"item" : "KS-JVM-715-SABC","client_id" : "P120","qty_ordered" : 9,"qty_received" : 0,"quantity_installed" : 0,"quantity_available" : 0}},{{"id" : 4,"item" : "KS-JVM-715-CURVADIS","client_id" : "P121","qty_ordered" : 2,"qty_received" : 0,"quantity_installed" : 0,"quantity_available" : 0}},]}}
 
Table: "install"
Columns: "id" [serial4], "room" [text], "product_available" [text], "prework" [text], "install" [text], "post_work" [text], "day_install_began" [text], "day_instal_complete" [text]
Sample database rows:
{{"install": [{{"id" : 1,"room" : "1607","product_available" : "NO","prework" : "NO","install" : "NO","post_work" : "NO","day_install_began" : "NaN","day_instal_complete" : "NaN"}},{{"id" : 2,"room" : "1608","product_available" : "NO","prework" : "NO","install" : "NO","post_work" : "NO","day_install_began" : "NaN","day_instal_complete" : "NaN"}},{{"id" : 3,"room" : "1609","product_available" : "NO","prework" : "NO","install" : "NO","post_work" : "NO","day_install_began" : "NaN","day_instal_complete" : "NaN"}},{{"id" : 4,"room" : "1610","product_available" : "NO","prework" : "NO","install" : "NO","post_work" : "NO","day_install_began" : "NaN","day_instal_complete" : "NaN"}},]}}
 
 
Table: "schedule"
Columns: "id" [serial4], "phase" [text], "floor" [text], "production_starts" [text], "production_ends" [text], "shipping_depature" [text], "shipping_arrival" [text], "custom_clearing_starts" [text], "custom_clearing_ends" [text], "arrive_on_site" [text], "pre_work_starts" [text], "pre_work_ends" [text], "install_starts" [text], "install_ends" [text], "post_work_starts" [text], "post_work_ends" [text], "floor_completed" [text], "floor_closes" [text], "floor_opens" [text]
Sample database rows:
{{"schedule": [{{"id" : 1,"phase" : "1","floor" : "16","production_starts" : "2025-03-11 00:00:00","production_ends" : "2025-06-19 00:00:00","shipping_depature" : "2025-06-20 00:00:00","shipping_arrival" : "2025-08-04 00:00:00","custom_clearing_starts" : "2025-08-04 00:00:00","custom_clearing_ends" : "2025-08-10 00:00:00","arrive_on_site" : "2025-08-11 00:00:00","pre_work_starts" : "2025-07-28 00:00:00","pre_work_ends" : "2025-08-11 00:00:00","install_starts" : "2025-08-11 00:00:00","install_ends" : "2025-08-25 00:00:00","post_work_starts" : "2025-08-25 00:00:00","post_work_ends" : "2025-09-01 00:00:00","floor_completed" : "2025-09-01 00:00:00","floor_closes" : "2025-07-28 00:00:00","floor_opens" : "2025-09-01 00:00:00"}},{{"id" : 2,"phase" : "1","floor" : "17","production_starts" : "2025-03-11 00:00:00","production_ends" : "2025-06-19 00:00:00","shipping_depature" : "2025-06-20 00:00:00","shipping_arrival" : "2025-08-04 00:00:00","custom_clearing_starts" : "2025-08-04 00:00:00","custom_clearing_ends" : "2025-08-10 00:00:00","arrive_on_site" : "2025-08-11 00:00:00","pre_work_starts" : "2025-07-28 00:00:00","pre_work_ends" : "2025-08-11 00:00:00","install_starts" : "2025-08-11 00:00:00","install_ends" : "2025-08-25 00:00:00","post_work_starts" : "2025-08-25 00:00:00","post_work_ends" : "2025-09-01 00:00:00","floor_completed" : "2025-09-01 00:00:00","floor_closes" : "2025-07-28 00:00:00","floor_opens" : "2025-09-01 00:00:00"}},{{"id" : 3,"phase" : "1","floor" : "18","production_starts" : "2025-03-11 00:00:00","production_ends" : "2025-06-19 00:00:00","shipping_depature" : "2025-06-20 00:00:00","shipping_arrival" : "2025-08-04 00:00:00","custom_clearing_starts" : "2025-08-04 00:00:00","custom_clearing_ends" : "2025-08-10 00:00:00","arrive_on_site" : "2025-08-11 00:00:00","pre_work_starts" : "2025-08-11 00:00:00","pre_work_ends" : "2025-08-25 00:00:00","install_starts" : "2025-08-25 00:00:00","install_ends" : "2025-09-08 00:00:00","post_work_starts" : "2025-09-08 00:00:00","post_work_ends" : "2025-09-15 00:00:00","floor_completed" : "2025-09-15 00:00:00","floor_closes" : "2025-08-11 00:00:00","floor_opens" : "2025-09-15 00:00:00"}},{{"id" : 4,"phase" : "1","floor" : "19","production_starts" : "2025-03-11 00:00:00","production_ends" : "2025-06-19 00:00:00","shipping_depature" : "2025-06-20 00:00:00","shipping_arrival" : "2025-08-04 00:00:00","custom_clearing_starts" : "2025-08-04 00:00:00","custom_clearing_ends" : "2025-08-10 00:00:00","arrive_on_site" : "2025-08-11 00:00:00","pre_work_starts" : "2025-08-11 00:00:00","pre_work_ends" : "2025-08-25 00:00:00","install_starts" : "2025-08-25 00:00:00","install_ends" : "2025-09-08 00:00:00","post_work_starts" : "2025-09-08 00:00:00","post_work_ends" : "2025-09-15 00:00:00","floor_completed" : "2025-09-15 00:00:00","floor_closes" : "2025-08-11 00:00:00","floor_opens" : "2025-09-15 00:00:00"}},]}}
                 
{}""".format(user_message)}
            ], gpt_model='gpt-4-1106-preview',json_required=False)
            print('output here ',prompt_first)




            
            if '{' in prompt_first:
                prompt_second="""You are an expert chatbot specializing in hotel furniture installation. Your task is to generate the most accurate and optimized SQL query based on the user's request, database schema, and context.
    
    Instructions:
        1.Carefully analyze the user query and determine the relevant tables and columns.
    
        2. Select the most appropriate tables for the query using the provided schema and related tables.
    
        3. Construct a well-structured SQL query that efficiently retrieves the required data which will be best fit according to User Query.
    
        4. Ensure accuracy and completeness, handling necessary joins, conditions, and filters.
    
    Database Schema:
    Available tables and columns:
    
    Available Tables & Schema:
    
    Table: "room_data"
    Columns: "id" [serial4], "room" [text], "floor" [text], "king" [text], "double" [text], "exec_king" [text], "bath_screen" [text], "room_model" [text], "left_desk" [text], "right_desk" [text], "to_be_renovated" [text], "descripton" [text]
    Sample database rows:
    {{"room_data": [ {{ "id" : 1, "room" : "1607", "floor" : "16", "king" : "YES", "double" : "NO", "exec_king" : "NO", "bath_screen" : "YES", "room_model" : "B", "left_desk" : "YES", "right_desk" : "NO", "to_be_renovated" : "YES", "description" : "King,  medium desk, w screen, custom ceiling and closet wall covering" }}, {{ "id" : 2, "room" : "1609", "floor" : "16", "king" : "NO", "double" : "YES", "exec_king" : "NO", "bath_screen" : "YES", "room_model" : "A LO", "left_desk" : "YES", "right_desk" : "NO", "to_be_renovated" : "YES", "description" : "Double, Long desk, w screen, custom ceiling and closet wall covering" }}, {{ "id" : 3, "room" : "1611", "floor" : "16", "king" : "YES", "double" : "NO", "exec_king" : "NO", "bath_screen" : "YES", "room_model" : "A COL", "left_desk" : "YES", "right_desk" : "NO", "to_be_renovated" : "YES", "description" : "King, Long desk, w screen, custom ceiling and closet wall covering" }}, {{ "id" : 4, "room" : "1613", "floor" : "16", "king" : "NO", "double" : "YES", "exec_king" : "NO", "bath_screen" : "YES", "room_model" : "A", "left_desk" : "YES", "right_desk" : "NO", "to_be_renovated" : "NO", "description" : "Double, Long desk, w screen, custom ceiling and closet wall covering" }}]}}
    
    Table: "room_model"
    Columns: "id" [serial4], "room_model" [text], "total" [text]
    Sample database rows:
    {{"room_model": [{{"id" : 1,"room_model" : "A","total" : "31"}},{{"id" : 2,"room_model" : "A COL","total" : "72"}},{{"id" : 3,"room_model" : "A LO","total" : "36"}},{{"id" : 4,"room_model" : "A LO DR","total" : "3"}},]}}
    
    
    Table: "product_data"
    Columns: "id" [serial4], "item" [text], "client_id" [text], "description" [text], "qty_ordered" [text], "price" [text], "client_selected" [text]
    Sample database rows:
    {{"product_data": [{{"id" : 1,"item" : "KS-JWM-113","client_id" : "P125","description" : "Desk\/Dining Chair","qty_ordered" : "320","price" : "255.0","client_selected" : "1"}},{{"id" : 2,"item" : "KS-JWM-702A","client_id" : "P123","description" : "Custom Dining Chair","qty_ordered" : "176","price" : "296.82","client_selected" : "1"}},{{"id" : 3,"item" : "KS-JVM-715-SABC","client_id" : "P120","description" : "Sofa SUITE A, B, C","qty_ordered" : "9","price" : "1646.6615384615384","client_selected" : "1"}},{{"id" : 4,"item" : "KS-JVM-715-CURVADIS","client_id" : "P121","description" : "Sofa CURVA DIS","qty_ordered" : "2","price" : "1646.6615384615384","client_selected" : "1"}}]}}
    
    
    Table: "product_room_model"
    Columns: "id" [serial4], "product_id" [int4], "room_model_id" [int4], "quantity" [int4]  
    Sample database rows:
    {{"product_room_model": [{{"id" : 1,"product_id" : 1,"room_model_id" : 1,"quantity" : 1}},{{"id" : 2,"product_id" : 1,"room_model_id" : 2,"quantity" : 1}},{{"id" : 3,"product_id" : 1,"room_model_id" : 3,"quantity" : 1}},{{"id" : 4,"product_id" : 1,"room_model_id" : 4,"quantity" : 1}},]}}
    
    Table: "inventory"
    Columns: "id" [serial4], "item" [text], "client_id" [text], "qty_ordered" [text], "qty_received" [text], "quantity_installed" [text], "quantity_available" [text]
    Sample database rows:
    {{"inventory": [{{"id" : 1,"item" : "KS-JWM-113","client_id" : "P125","qty_ordered" : 320,"qty_received" : 0,"quantity_installed" : 0,"quantity_available" : 0}},{{"id" : 2,"item" : "KS-JWM-702A","client_id" : "P123","qty_ordered" : 176,"qty_received" : 0,"quantity_installed" : 0,"quantity_available" : 0}},{{"id" : 3,"item" : "KS-JVM-715-SABC","client_id" : "P120","qty_ordered" : 9,"qty_received" : 0,"quantity_installed" : 0,"quantity_available" : 0}},{{"id" : 4,"item" : "KS-JVM-715-CURVADIS","client_id" : "P121","qty_ordered" : 2,"qty_received" : 0,"quantity_installed" : 0,"quantity_available" : 0}},]}}
    
    Table: "install"
    Columns: "id" [serial4], "room" [text], "product_available" [text], "prework" [text], "install" [text], "post_work" [text], "day_install_began" [text], "day_instal_complete" [text]
    Sample database rows:
    {{"install": [{{"id" : 1,"room" : "1607","product_available" : "NO","prework" : "NO","install" : "NO","post_work" : "NO","day_install_began" : "NaN","day_instal_complete" : "NaN"}},{{"id" : 2,"room" : "1608","product_available" : "NO","prework" : "NO","install" : "NO","post_work" : "NO","day_install_began" : "NaN","day_instal_complete" : "NaN"}},{{"id" : 3,"room" : "1609","product_available" : "NO","prework" : "NO","install" : "NO","post_work" : "NO","day_install_began" : "NaN","day_instal_complete" : "NaN"}},{{"id" : 4,"room" : "1610","product_available" : "NO","prework" : "NO","install" : "NO","post_work" : "NO","day_install_began" : "NaN","day_instal_complete" : "NaN"}},]}}
    
    
    Table: "schedule"
    Columns: "id" [serial4], "phase" [text], "floor" [text], "production_starts" [text], "production_ends" [text], "shipping_depature" [text], "shipping_arrival" [text], "custom_clearing_starts" [text], "custom_clearing_ends" [text], "arrive_on_site" [text], "pre_work_starts" [text], "pre_work_ends" [text], "install_starts" [text], "install_ends" [text], "post_work_starts" [text], "post_work_ends" [text], "floor_completed" [text], "floor_closes" [text], "floor_opens" [text]
    Sample database rows:
    {{"schedule": [{{"id" : 1,"phase" : "1","floor" : "16","production_starts" : "2025-03-11 00:00:00","production_ends" : "2025-06-19 00:00:00","shipping_depature" : "2025-06-20 00:00:00","shipping_arrival" : "2025-08-04 00:00:00","custom_clearing_starts" : "2025-08-04 00:00:00","custom_clearing_ends" : "2025-08-10 00:00:00","arrive_on_site" : "2025-08-11 00:00:00","pre_work_starts" : "2025-07-28 00:00:00","pre_work_ends" : "2025-08-11 00:00:00","install_starts" : "2025-08-11 00:00:00","install_ends" : "2025-08-25 00:00:00","post_work_starts" : "2025-08-25 00:00:00","post_work_ends" : "2025-09-01 00:00:00","floor_completed" : "2025-09-01 00:00:00","floor_closes" : "2025-07-28 00:00:00","floor_opens" : "2025-09-01 00:00:00"}},{{"id" : 2,"phase" : "1","floor" : "17","production_starts" : "2025-03-11 00:00:00","production_ends" : "2025-06-19 00:00:00","shipping_depature" : "2025-06-20 00:00:00","shipping_arrival" : "2025-08-04 00:00:00","custom_clearing_starts" : "2025-08-04 00:00:00","custom_clearing_ends" : "2025-08-10 00:00:00","arrive_on_site" : "2025-08-11 00:00:00","pre_work_starts" : "2025-07-28 00:00:00","pre_work_ends" : "2025-08-11 00:00:00","install_starts" : "2025-08-11 00:00:00","install_ends" : "2025-08-25 00:00:00","post_work_starts" : "2025-08-25 00:00:00","post_work_ends" : "2025-09-01 00:00:00","floor_completed" : "2025-09-01 00:00:00","floor_closes" : "2025-07-28 00:00:00","floor_opens" : "2025-09-01 00:00:00"}},{{"id" : 3,"phase" : "1","floor" : "18","production_starts" : "2025-03-11 00:00:00","production_ends" : "2025-06-19 00:00:00","shipping_depature" : "2025-06-20 00:00:00","shipping_arrival" : "2025-08-04 00:00:00","custom_clearing_starts" : "2025-08-04 00:00:00","custom_clearing_ends" : "2025-08-10 00:00:00","arrive_on_site" : "2025-08-11 00:00:00","pre_work_starts" : "2025-08-11 00:00:00","pre_work_ends" : "2025-08-25 00:00:00","install_starts" : "2025-08-25 00:00:00","install_ends" : "2025-09-08 00:00:00","post_work_starts" : "2025-09-08 00:00:00","post_work_ends" : "2025-09-15 00:00:00","floor_completed" : "2025-09-15 00:00:00","floor_closes" : "2025-08-11 00:00:00","floor_opens" : "2025-09-15 00:00:00"}},{{"id" : 4,"phase" : "1","floor" : "19","production_starts" : "2025-03-11 00:00:00","production_ends" : "2025-06-19 00:00:00","shipping_depature" : "2025-06-20 00:00:00","shipping_arrival" : "2025-08-04 00:00:00","custom_clearing_starts" : "2025-08-04 00:00:00","custom_clearing_ends" : "2025-08-10 00:00:00","arrive_on_site" : "2025-08-11 00:00:00","pre_work_starts" : "2025-08-11 00:00:00","pre_work_ends" : "2025-08-25 00:00:00","install_starts" : "2025-08-25 00:00:00","install_ends" : "2025-09-08 00:00:00","post_work_starts" : "2025-09-08 00:00:00","post_work_ends" : "2025-09-15 00:00:00","floor_completed" : "2025-09-15 00:00:00","floor_closes" : "2025-08-11 00:00:00","floor_opens" : "2025-09-15 00:00:00"}},]}}
    
    User Query:

    {}
    
    Relevant Context Tables and Columns:
    Helpful references for query construction:

    {}



    **strictly remember i need a sql query in json format with key 'query' and values as sql query**
    """.format(user_message,prompt_first)
                # GPT API Call
                response = json.loads(gpt_call_json_func([
                    {'role': 'system', 'content': prompt_second }
                ], gpt_model='gpt-4o'))
                
                rows=fetch_data_from_sql(response['query'])
                final_response=gpt_call_json_func([
                    {'role': 'system', 'content': finalised_response_prompt.format(user_message,response['query'],rows)}], gpt_model='gpt-4o',json_required=False)
                bot_message=final_response
                print(prompt_second,final_response)
            else:
                bot_message=prompt_first


           
        except Exception as e:
                try:
                    print("got error : now making new query")
                    response = json.loads(gpt_call_json_func([
                        {'role': 'system', 'content': prompt_second },
                        {'role': 'assistant', 'content': response['query'] },
                        {'role': 'user', 'content': f'I got error please fix it \n\n {e}' },
                    ], gpt_model='gpt-4o'))
                    
                    rows=fetch_data_from_sql(response['query'])
                    final_response=gpt_call_json_func([
                        {'role': 'system', 'content': finalised_response_prompt.format(user_message,response['query'],rows)}], gpt_model='gpt-4o',json_required=False)
                    bot_message=final_response
                    print(prompt_second,final_response)
                except:   
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

@login_required       
def room_data_list(request):
    # Fetch room data from the database
    rooms = RoomData.objects.all()

    # Pass the room data to the template
    return render(request, 'room_data_list.html', {'rooms': rooms})

@login_required
def get_room_models(request):
    room_models = RoomModel.objects.all()
    room_model_list = [{"id": model.id, "name": model.room_model} for model in room_models]
    return JsonResponse({"room_models": room_model_list})

@login_required
def add_room(request):
    if request.method == 'POST':
        room_number = request.POST.get('room')
        floor = request.POST.get('floor')
        king = request.POST.get('king')
        double = request.POST.get('double')
        exec_king = request.POST.get('exec_king')
        bath_screen = request.POST.get('bath_screen')
        left_desk = request.POST.get('left_desk')
        right_desk = request.POST.get('right_desk')
        to_be_renovated = request.POST.get('to_be_renovated')
        room_model_id = request.POST.get('room_model')
        description = request.POST.get('description')

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
                description=description
            )
            return JsonResponse({'success': 'Room added successfully'})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)


@login_required
def edit_room(request):
    if request.method == 'POST':
        try:
            room_id = request.POST.get('room_id')
            room = get_object_or_404(RoomData, id=room_id)

            # Don't update room number
            room.floor = request.POST.get('floor')
            room.king = request.POST.get('king')
            room.double = request.POST.get('double')
            room.exec_king = request.POST.get('exec_king')
            room.bath_screen = request.POST.get('bath_screen')
            room.description = request.POST.get('description')
            room.left_desk = request.POST.get('left_desk')
            room.right_desk = request.POST.get('right_desk')
            room.to_be_renovated = request.POST.get('to_be_renovated')

            # Update Room Model if given
            room_model_id = request.POST.get('room_model')
            if room_model_id:
                room_model = get_object_or_404(RoomModel, id=room_model_id)
                room.room_model = room_model.room_model
                room.room_model_id = room_model
                print("room = ",room_model)

            room.save()

            return JsonResponse({'success': 'Room updated successfully!'})

        except RoomModel.DoesNotExist:
            return JsonResponse({'error': 'Invalid room model!'}, status=400)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)

    return JsonResponse({'error': 'Invalid request'}, status=400)

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
    return render(request, 'room_model_list.html', {'room_models': room_models})


@login_required
def save_room_model(request):
    if request.method == 'POST':
        model_id = request.POST.get('model_id')
        name = request.POST.get('name').strip()

        if not name:
            return JsonResponse({'error': 'Model name is required'}, status=400)

        # Check for duplicate name (case-insensitive)
        existing_model = RoomModel.objects.filter(room_model__iexact=name)
        if model_id:
            existing_model = existing_model.exclude(id=model_id)

        if existing_model.exists():
            return JsonResponse({'error': 'A room model with this name already exists.'}, status=400)

        if model_id:
            try:
                model = RoomModel.objects.get(id=model_id)
                model.room_model = name
                model.save()
                return JsonResponse({'success': 'Room model updated successfully'})
            except RoomModel.DoesNotExist:
                return JsonResponse({'error': 'Room model not found'}, status=404)
        else:
            RoomModel.objects.create(room_model=name)
            return JsonResponse({'success': 'Room model created successfully'})

    return JsonResponse({'error': 'Invalid request'}, status=400)



@login_required
def delete_room_model(request):
    if request.method == 'POST':
        model_id = request.POST.get('model_id')
        try:
            room_model = RoomModel.objects.get(id=model_id)
            room_model.delete()
            return JsonResponse({'success': 'Room Model deleted.'})
        except RoomModel.DoesNotExist:
            return JsonResponse({'error': 'Room Model not found.'})
    return JsonResponse({'error': 'Invalid request.'})
