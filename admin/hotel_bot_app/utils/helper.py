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
    # Enhanced system prompt for SQL Generation
    system_prompt = """
    You are an expert SQL generation assistant named PksBot, specializing in PostgreSQL for a hotel furniture installation database.

    **Core Responsibilities:**
    1.  **Analyze User Intent:** Understand the user's request thoroughly.
    2.  **Generate Accurate PostgreSQL:** Create precise and efficient SQL queries based on the provided schema.
    3.  **Use Human-Readable Data:** Prioritize returning meaningful names/descriptions over IDs. JOIN tables when necessary (e.g., join `ProductData` on `id` with `InstallDetail` on `product_id`).
    4.  **Case-Insensitive Search:** ALWAYS use `ILIKE` for string comparisons involving names, descriptions, or any potentially case-variable text. Example: `WHERE item ILIKE '%sofa%'`.
    5.  **Avoid Type Mismatches:** Ensure correct data types in comparisons (string vs. numeric).
    6.  **Safety & Performance:** ALWAYS include a `LIMIT` clause (e.g., `LIMIT 50`) to prevent overly large results.
    7.  **Strict Schema Adherence:** ONLY use tables and columns defined in the provided schema. Do NOT hallucinate.
    8.  **JSON Output:** Return ONLY a valid JSON object containing the SQL query. Format: `{"query": "SELECT ... FROM ... WHERE ... ILIKE ... LIMIT 50;"}`.
    9.  **No Explanations:** Do not add any explanations, markdown, or code blocks outside the JSON structure.

    **Schema Information (including examples):**
    The database schema, including example rows for context, is provided below. Use it as your single source of truth for table and column names.
    """

    # Convert prompt_data (loaded YAML with examples) to a readable JSON string for the prompt
    schema_representation = json.dumps(prompt_data, indent=2)

    return [
        {"role": "system", "content": system_prompt.strip()},
        {"role": "system", "content": f"Database Schema:\\n```json\\n{schema_representation}\\n```"}, # Wrap schema in markdown for clarity
        {"role": "user", "content": f"User Query:\\n{user_message.strip()}"},
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
    # --- Input Validation ---
    if rows is None:
        # This can happen if SQL generation failed, execution failed irrecoverably, or no query was needed.
        # The chatbot_api view should ideally handle the specific reason, but this function can provide a fallback.
        print("generate_final_response called with rows=None. Returning generic error or 'no data' message.")
        # Option 1: Generic error (if None implies an upstream failure)
        # return "Sorry, I couldn't retrieve the data needed to answer your question."
        # Option 2: Treat as 'no data' (if None might mean no query was applicable/run)
        return "No records found matching your query."
    elif not isinstance(rows, dict):
        print(f"Error: generate_final_response received 'rows' of unexpected type: {type(rows)}. Expected dict.")
        return "Sorry, there was an internal error processing the data."

    # --- Data Extraction ---
    columns = rows.get('columns', [])
    data = rows.get('rows', [])
    num_records = len(data) if isinstance(data, (list, tuple)) else 0 # Ensure data is iterable

    # --- Prompt Definition ---
    # Enhanced system prompt for Final Response Generation
    prompt = f"""
    You are PksBot, a helpful assistant presenting query results for a hotel furniture installation system.

    **Your Task:** Convert the provided SQL query results into a user-friendly format, strictly adhering to the rules below.

    **Input:**
    - User's original query: "{user_message}"
    - Query results:
        - Columns: {columns if columns else 'N/A'}
        - Number of Records: {num_records}
        - Data (list of tuples/lists): {str(data) if data else 'None'}

    **Output Rules:**
    1.  **Data Found (num_records > 0):**
        - Generate ONLY an HTML `<table>`.
        - Use the exact `columns` provided for the table headers (`<thead><tr><th>...</th></tr></thead>`).
        - Populate the table body (`<tbody>`) with the `data`. Each inner list/tuple in `data` is a row (`<tr>`), and each item within it is a cell (`<td>`).
        - Escape HTML special characters within data cells (e.g., '<', '>') to prevent XSS issues.
        - Example Structure:
          ```html
          <table>
            <thead>
              <tr><th>Column1</th><th>Column2</th></tr>
            </thead>
            <tbody>
              <tr><td>Row1Val1</td><td>Row1Val2</td></tr>
              <tr><td>Row2Val1</td><td>Row2Val2</td></tr>
            </tbody>
          </table>
          ```
    2.  **No Data Found (num_records == 0):**
        - Return ONLY the text string: "No records found matching your query." (Do not include the original query here).
    3.  **Non-Data/General Queries (if applicable, though primary focus is data):**
        - If the user query wasn't expected to return data (e.g., a greeting), provide a concise, relevant answer in one sentence. *This case is less likely given the SQL generation flow.*
    4.  **Strict Prohibitions:**
        - **NO** introductory text (e.g., "Here are the results:").
        - **NO** concluding text or summaries.
        - **NO** apologies or explanations.
        - **NO** markdown formatting (like ```html ... ```). Output raw HTML for tables or plain text for "no records".
        - **NO** modifications to column names or data values.
        - **NO** invention of data.

    **Generate the precise output based ONLY on the rules and the provided data.**
    """
    # --- Message Preparation ---
    message = [
        {"role": "system", "content": prompt.strip()},
        # The user message here provides context for the *final* LLM call, but the main data is in the system prompt.
        {"role": "user", "content": f"Present the results for the user query: {user_message}"}
    ]
    # --- LLM Call ---
    try:
        # Call the output parser GPT
        response = output_praser_gpt(
            message,
            gpt_model="gpt-4o",
            json_required=False, # Expecting HTML or plain text, not JSON
            temperature=0.0,     # Keep deterministic for formatting
        )
        # --- Response Validation ---
        if not response or not isinstance(response, str):
             print(f"Error: output_praser_gpt in generate_final_response returned invalid data: {response}")
             return "Sorry, I couldn't format the response correctly."
        return response

    except Exception as e:
        print(f"Error calling output_praser_gpt within generate_final_response: {e}")
        return "Sorry, an error occurred while formatting the final response."


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

    # Enhanced prompt for SQL Verification
    prompt = f"""
    You are PksBot, a PostgreSQL validation and debugging expert for a hotel furniture installation system.

    **Objective:** Validate the provided SQL query against the user's intent, the database schema, and any reported database error. If the query is invalid or suboptimal, provide a corrected version.

    **Input Details:**
    1.  **User Message:** {user_message}
    2.  **Original SQL Query:** {sql_query}
    3.  **Database Schema (with examples):** \n```json\n{json.dumps(prompt_data, indent=2)}\n```
    4.  **Database Error Message (if any):** {error_message or "None"}

    **Analysis Checklist:**
    - **Syntax:** Is the SQL syntax correct for PostgreSQL?
    - **Schema Adherence:** Does the query use valid table and column names from the schema?
    - **Joins:** Are joins logical and correctly implemented (if needed)?
    - **Conditions:** Do `WHERE` clauses correctly reflect the user's intent? Are data types matched correctly (e.g., string vs. number)? Is `ILIKE` used for case-insensitive text comparison where appropriate?
    - **Intent Alignment:** Does the query accurately address the user's message?
    - **Error Relevance:** If an error message is provided, does the query address the likely cause?

    **Output Format:**
    Respond ONLY with a single, valid JSON object. Do NOT include any explanations, apologies, or text outside the JSON structure.
    The JSON object MUST have the following structure:
    ```json
    {{
      "is_valid": boolean, // true if the ORIGINAL query is perfectly valid and optimal, otherwise false
      "issues": [ // List of strings describing the problems found. Empty list if is_valid is true.
        "Example: Type mismatch in WHERE clause.",
        "Example: Missing JOIN to retrieve readable name."
      ],
      "recommendation": string | null // The corrected/improved SQL query if issues were found (is_valid is false), otherwise null.
    }}
    ```

    **Example Valid Scenario:**
    If the original query is `SELECT room FROM RoomData WHERE floor = 5 LIMIT 50;` and it's correct:
    ```json
    {{
      "is_valid": true,
      "issues": [],
      "recommendation": null
    }}
    ```

    **Example Invalid Scenario:**
    If the original query is `SELECT name FROM Inventory WHERE qty_received = '10';` (type mismatch) for user message "show items with 10 received":
    ```json
    {{
      "is_valid": false,
      "issues": [
        "Type mismatch: qty_received is numeric but compared against a string '10'.",
        "Potentially ambiguous column 'name'; consider specifying table if joins are possible."
      ],
      "recommendation": "SELECT item FROM Inventory WHERE qty_received = 10 LIMIT 50;"
    }}
    ```

    **Generate the JSON response now.**
    """

    try:
        # Use the dedicated function, ensuring JSON is expected
        response_str = output_praser_gpt(
            [{"role": "user", "content": prompt.strip()}], # Pass the structured prompt
            gpt_model=gpt_model,
            json_required=True,
            temperature=0.1, # Low temperature for deterministic validation
        )

        # Parse the string response into JSON
        if isinstance(response_str, str):
            return json.loads(response_str)
        elif isinstance(response_str, dict): # If output_praser_gpt already parsed it (less likely now)
             return response_str
        else:
            # Handle unexpected response type from output_praser_gpt
            print(f"SQL verification: Unexpected response type from output_praser_gpt: {type(response_str)}")
            raise ValueError("Unexpected response format during verification.")

    except json.JSONDecodeError as json_err:
        print(f"SQL verification JSON decode error: {json_err}")
        print(f"Raw response received for verification: {response_str}") # Log the raw response
        return {
            "is_valid": False,
            "issues": ["Failed to parse the validation response from the AI."],
            "recommendation": None,
        }
    except Exception as e:
        print(f"SQL verification error: {e}")
        return {
            "is_valid": False,
            "issues": [f"An unexpected error occurred during SQL verification: {str(e)}"],
            "recommendation": None,
        }
