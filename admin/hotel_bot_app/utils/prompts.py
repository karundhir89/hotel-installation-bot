import json
import os
import re

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
        return cursor.fetchall()


def format_gpt_prompt(user_message, prompt_data):
    return f"""
You are an expert chatbot specializing in hotel furniture installation and your name is PksBot bot. 

Your job is to analyze the user query and generate a valid SQL query if there is need to do otherwise answer as specialize chatbot for hi hello and general queries that not just retrieve the raw information from database but can be human understandable like if searching for prodcuts then return the name instead of their id or other kind of indetifiers and so the same in other queries that can be run on the following database schema. 

### User Query:
{user_message}

### Schema:
{json.dumps(prompt_data, indent=2)}

### Rules:
- Return only a valid SQL query.
- Do not explain anything.
- Query should be good enough to tell what about this is and the real information and a layman needs to understand
- The response must be a JSON object with this format:
- Also must take care of type casts dont query wrong type to wrong fields like searching chiar with numberic fields don't do that
- For matching any given product name use iLike and retuned the best matches
- Always use limit parameter and use the best practice whie generating query and also try to more focus on indexes for fasta access
- Aslo you can use pagination if needed
{{
  "query": "SQL_QUERY_STRING_HERE"
}}

Respond only with the JSON object.
"""


def gpt_call_json_func(message, gpt_model, json_required=True, temperature=0):
    try:
        json_payload = {
            "model": gpt_model,
            "temperature": temperature,
            "messages": message,
        }

        if json_required:
            json_payload["response_format"] = {"type": "json_object"}

        gpt_response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            json=json_payload,
            headers={
                "Authorization": f"Bearer {open_ai_key}",
                "Content-Type": "application/json",
            },
        )

        raw_content = gpt_response.json()["choices"][0]["message"]["content"]

        # Only clean if triple backticks exist
        if "```" in raw_content:
            raw_content = re.sub(r"```json|```", "", raw_content).strip()

        # Try parsing JSON
        return json.loads(raw_content)

    except Exception as e:
        print("gpt call error:", e)
        return {"query": None}


def output_parser(message, gpt_model, json_required=True, temperature=0.3):
    try:
        json_payload = {
            "model": gpt_model,
            "temperature": temperature,
            "messages": message,
        }

        if json_required:
            json_payload["response_format"] = {"type": "json_object"}

        gpt_response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            json=json_payload,
            headers={
                "Authorization": f"Bearer {open_ai_key}",
                "Content-Type": "application/json",
            },
        )

        raw_content = gpt_response.json()["choices"][0]["message"]["content"]

        # Remove triple backticks and optional "json" tag
        cleaned = re.sub(r"```json|```", "", raw_content).strip()

        # Try to parse as JSON
        return json.loads(cleaned)

    except Exception as e:
        print("gpt call error", e)
        return {"query": None}


def generate_final_response(user_message, rows):

    prompt = f"""
    You are an HTML-generating assistant.
    your name is PksBot bot.

    ⚠️ You must return only **valid raw HTML**. Never use Markdown, backticks, code blocks, or any formatting language. Only pure HTML tags.

    🧠 User asked: "{user_message}"
    📦 Database context: "{rows}"

    Your job:
    1. Parse the context data and present it as a clean HTML table.
    2. Do not return any explanation, intro, summary, or additional text.
    3. Always use this format exactly: if data seems to be tabular else return simple text

    <table>
    <thead>
        <tr>
        <th>Item</th>
        <th>Quantity</th>
        </tr>
    </thead>
    <tbody>
        <tr>
        <td>Ceiling Beam at Executive Suite CURVA DIS</td>
        <td>2 units left</td>
        </tr>
        <tr>
        <td>Wood Wall Cladding - model SUITE MINI</td>
        <td>1 unit left</td>
        </tr>
        ...
    </tbody>
    </table>

    🛑 Absolutely NO:
    - Markdown
    - Backticks (``` or `)
    - Code tags like <code> or <pre>
    - Quotes around HTML
    - Text outside the table

    📌 If no data exists, return a just text with a helpful answer without any html tag.
        and if asked some general question response generally
    💡 Treat the response as something that will be injected directly into a live web page.
    """


    # Send to GPT
    gpt_summary = output_praser_gpt(
        [{"role": "user", "content": prompt}],
        gpt_model="gpt-4o",
        json_required=False,
        temperature=0.4,
    )

    return gpt_summary


def output_praser_gpt(message, gpt_model, json_required=True, temperature=0):
    try:
        json_payload = {
            "model": gpt_model,
            "temperature": temperature,
            "messages": message,
        }

        if json_required:
            json_payload["response_format"] = {"type": "json_object"}

        gpt_response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            json=json_payload,
            headers={
                "Authorization": f"Bearer {open_ai_key}",
                "Content-Type": "application/json",
            },
        )

        raw_content = gpt_response.json()["choices"][0]["message"]["content"]

        return raw_content

    except Exception as e:
        print("gpt call error:", e)
        return {"query": None}

def verify_sql_query(user_message, sql_query, prompt_data, error_message=None, gpt_model="gpt-4o"):
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
