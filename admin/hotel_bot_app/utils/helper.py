import json
import os
import re

import json
import re
import requests
import environ
import requests
import yaml
from django.db import connection
from openai import OpenAI

env = environ.Env()
environ.Env.read_env()
open_ai_key = env("open_ai_api_key")

client = OpenAI(api_key=open_ai_key)


def load_database_schema():
    base_dir = os.path.dirname(__file__)  # This points to hotel_bot_app/utils
    schema_path = os.path.join(base_dir, "db_schema.yaml")

    with open(schema_path, "r") as file:
        return yaml.safe_load(file)


def fetch_data_from_sql(query):
    with connection.cursor() as cursor:
        cursor.execute(query)
        columns = [col[0] for col in cursor.description]
        rows = cursor.fetchall()
        return {
            "columns": columns,
            "rows": rows
        }


def format_gpt_prompt(user_message, prompt_data):
    system_prompt = """
    You are an expert chatbot specializing in hotel furniture installation. Your name is PksBot.

    Your responsibilities:
    - Understand the user's message.
    - Always use iLike for finding string either yes or YES or Yes or Sofa or any product name
    - If the query requires data, generate a valid SQL query.
    - Make sure SQL returns human-readable values (like names, not IDs).
    - Avoid incorrect type matching (e.g., string vs numeric mismatches).
    - Match product names using `iLike` and return best matches.
    - Always include a LIMIT clause for performance and pagination readiness.
    - Don't explain, just return a JSON response with SQL.
    - Format: {"query": "SQL_QUERY_STRING_HERE"}
    - Do not hallucinate table or column names.
    - Avoid using markdown or code blocks.
    - Focus on best practices: indexes, joins, readability.
    """

    return [
        {"role": "system", "content": system_prompt.strip()},
        {"role": "System", "content": f"Database Schema:\n{json.dumps(prompt_data, indent=2)}"},
        {"role": "user", "content": f"User Query:\n{user_message.strip()}"},
    ]


def gpt_call_json_func(message, gpt_model, json_required=False, temperature=0):
    try:
        # Ensure all 'role' fields in the message are lowercase (standardize to 'system', 'user', etc.)
        for msg in message:
            if 'role' in msg:
                msg['role'] = msg['role'].lower()  # Normalize role to lowercase

        # Prepare the JSON payload for the GPT API request
        json_payload = {
            "model": gpt_model,
            "temperature": temperature,
            "messages": message,
        }

        if json_required:
            json_payload["response_format"] = {"type": "json_object"}

        # Send request to GPT API
        gpt_response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            json=json_payload,
            headers={
                "Authorization": f"Bearer {open_ai_key}",
                "Content-Type": "application/json",
            },
        )

        # Check for successful response status
        if gpt_response.status_code != 200:
            print(f"Error: Received status code {gpt_response.status_code}")
            return {"query": None}

        # Extract content from the response
        raw_content = gpt_response.json().get("choices", [{}])[0].get("message", {}).get("content", "")
        
        # If content has code blocks, remove triple backticks
        if "```" in raw_content:
            raw_content = re.sub(r"```json|```", "", raw_content).strip()

        # Try parsing the content into a JSON object
        try:
            return json.loads(raw_content)
        except json.JSONDecodeError:
            print("Error: Failed to decode the JSON response.")
            return {"query": None}

    except requests.exceptions.RequestException as e:
        print(f"Request error: {e}")
        return {"query": None}
    except Exception as e:
        print(f"Unexpected error: {e}")
        return {"query": None}


def generate_final_response(user_message, rows):
    # Ensure rows are properly structured
    columns = rows.get('columns', [])
    data = rows.get('rows', [])
    
    # Initialize the prompt
    prompt = f"""
    You are PksBot, a hotel furniture installation assistant. Strictly follow these rules:

    ### Rules:
    1. Data Presentation:
       - If data exists: Create HTML table using Table tags:
         <table>
           <thead><tr></tr></thead>
           <tbody><tr><td></td></tr>
           </tbody>
         </table>
       - If no data: "No records found matching: {user_message}"
       - For non-data queries: Answer concisely in 1 sentence

    2. Strict Prohibitions:
       - Never invent data beyond what's provided
       - No markdown, backticks, or code blocks
       - No explanations or apologies
       - Never modify column names or order
       - Never infer or calculate values

    """
    message = [{"role": "system", "content": prompt},{"role": "user", "content": f"""
    User Query: {user_message}
    ### Current Data:
    Columns: {columns if columns else 'N/A'}
    Records Found: {len(data) if data else 0}
    Data: {str(data) if data else 'None'}
    """}]
    # if rows:
    #     content_data = {"role":"system", "content":rows}
    #     message.append(content_data)
    
    # Call the output parser with the prompt
    return output_praser_gpt(
        message,
        gpt_model="gpt-4o",
        json_required=False,
        temperature=0.0,
    )


def output_praser_gpt(message, gpt_model, json_required=True, temperature=0):
    try:
        # Ensure all 'role' fields in the message are lowercase (standardize to 'system', 'user', etc.)
        for msg in message:
            if 'role' in msg:
                msg['role'] = msg['role'].lower()  # Normalize role to lowercase

        # Prepare the JSON payload for the GPT API request
        json_payload = {
            "model": gpt_model,
            "temperature": temperature,
            "messages": message,
        }

        if json_required:
            json_payload["response_format"] = {"type": "json_object"}

        # Send request to GPT API
        gpt_response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            json=json_payload,
            headers={
                "Authorization": f"Bearer {open_ai_key}",
                "Content-Type": "application/json",
            },
        )

        # Check for successful response status
        if gpt_response.status_code != 200:
            print(f"Error: Received status code {gpt_response.status_code}")
            print(f"Response body: {gpt_response.text}")
            return {"query": None}

        # Extract content from the response
        raw_content = gpt_response.json().get("choices", [{}])[0].get("message", {}).get("content", "")

        # Log raw response content for debugging
        print(f"Raw GPT response content: {raw_content}")

        if "```" in raw_content:
            raw_content = re.sub(r"```json|```", "", raw_content).strip()
        return raw_content

    except requests.exceptions.RequestException as e:
        print(f"Request error: {e}")
        return {"query": None}
    except Exception as e:
        print(f"Unexpected error: {e}")
        return {"query": None}

def verify_sql_query(
    user_message, sql_query, prompt_data, error_message=None, gpt_model="gpt-4o"
):
    """
    Verifies the SQL query for correctness, data type casting, structure, and intent alignment.
    Also considers DB error messages like type mismatch.
    """

    prompt = f"""
        You are a SQL validation and debugging expert for hotel furniture installation systems.
        your name is PksBot bot.

        Your job is to:
        - Review the user message, SQL query, schema, and any error message.
        - Spot logical, syntactic, and type-related problems.
        - Provide a structured JSON output showing whether the query is valid.
        - Suggest a corrected version of the query if needed.

        ## User Message:
        {user_message}

        ## SQL Query:
        {sql_query}

        ## Schema:
        {json.dumps(prompt_data, indent=2)}

        ## Database Error (if any):
        {error_message or "None"}

        ## Output JSON format:
        {{
        "is_valid": true | false,
        "issues": ["describe what is wrong, e.g., type mismatch or bad join"],
        "recommendation": "Provide a fixed or improved SQL query (if applicable), or null"
        }}

        Respond with ONLY a valid JSON object. No other explanations.
    """

    try:
        response = output_praser_gpt(
            [{"role": "user", "content": prompt}],
            gpt_model=gpt_model,
            json_required=True,
            temperature=0.2,
        )

        return json.loads(response) if isinstance(response, str) else response

    except Exception as e:
        print("SQL verification error:", e)
        return {
            "is_valid": False,
            "issues": ["Could not parse GPT response."],
            "recommendation": None,
        }
