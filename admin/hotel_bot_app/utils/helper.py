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



def gpt_call_json_func_two(message,gpt_model,openai_key,json_required=True,temperature=0):
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
				'Authorization': f'Bearer {openai_key}',
				'Content-Type': 'application/json'
			}
		)
		print("gpt response got is ",gpt_response.json())
		print("gpt function ended with ....",gpt_response.json()['choices'][0]['message']['content'])
		# print("gpt response got is ",gpt_response.json()['choices'])
		return gpt_response.json()['choices'][0]['message']['content']
	except Exception as e:
		print("gpt call error",e)

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

# New function for the initial Intent + Conditional SQL Generation Prompt

def format_intent_sql_prompt(user_message, prompt_data):
    """Formats the prompt for the initial LLM call to determine intent and generate SQL if needed."""
    schema_representation = json.dumps(prompt_data, indent=2)

    # Indent the schema representation for better formatting within the f-string
    indented_schema = "\n".join("  " + line for line in schema_representation.splitlines())

    system_prompt = f"""
        You are PksBot, an AI assistant specialized in querying a PostgreSQL database for a hotel furniture installation and renovation system. Your primary role is to understand user queries and return either a precise SQL query or a natural language response.

        ---

        ## Analysis Steps:

        1. **Understand Intent:** Carefully interpret the user’s query: "{user_message}"
        2. **Check Database Need:**
            - If the user asks for information that involves specific data (inventory, schedules, room status, etc.), a SQL query is needed.
            - If it’s a general greeting, instruction, or system question, respond naturally without using the database.
        3. **Respond Accordingly:**
            - **If SQL is Needed:** Generate a valid, safe PostgreSQL query using the schema, rules, and relationships below.
            - **If NOT Needed:** Respond in natural language, concisely and clearly.

        ---

        ## Database Schema and Query Guidelines:

        **Context:**  
        This database manages hotel room models, furniture inventory, installation progress, and scheduling.

        ---

        ### Key Table Relationships and Join Logic:

        - **Product Schedule (by product description):**
            1. `product_data.description` → `product_data.id`
            2. `JOIN product_room_model ON product_data.id = product_room_model.product_id`
            3. `JOIN room_model ON product_room_model.room_model_id = room_model.id`
            4. `JOIN room_data ON room_model.id = room_data.room_model_id`
            5. `JOIN schedule ON room_data.floor = schedule.floor`

        - **Inventory and Product Names:**
            1. `JOIN inventory inv ON inv.client_id = product_data.client_id`
            2. Access `inv.quantity_available`, `inv.qty_received`, `product_data.description`

        - **Installation Progress by Room:**
            1. `JOIN install ON install.room = room_data.room`

        ---

        ### SQL Generation Rules:

        - **Schema Adherence:** Use only provided tables and columns. Match data types strictly.
        - **Readable Aliases:** Use clear aliases (e.g., `inv` for `inventory`, `pd` for `product_data`).
        - **Human-Friendly Results:** Prefer names/descriptions over IDs.
        - **String Matching:** Use `ILIKE` for case-insensitive comparisons.
        - **Date Logic:** Compare dates (e.g., schedule completion) with `NOW()`.
        - **Limit Results:** Always append `LIMIT 50` unless told otherwise.
        - **Room Models rule:** Strictly use only below room models donot go outside these ones
            - 'A COL', 'A LO', 'A LO DR', 'B', 'C PN', 'C+', 'CURVA 24', 'CURVA', 'CURVA - DIS', 'D', 'DLX', 'STC', 'SUITE A', 'SUITE B', 'SUITE C', 'SUITE MINI', 'CURVA 35', 'PRESIDENTIAL SUITE', 'Test Room'
        

        ---

        ### Aggregation Rules:


        Only use aggregate functions (`SUM`, `COUNT`, `AVG`, etc.) if the user explicitly asks for:
        - Totals, averages, summaries
        - Grouped insights (e.g., "Which rooms have completed installations?")

        Avoid aggregation if the user wants specific items or detailed records.

        ---

        ### Safety and Restrictions:

        - **Read-Only Queries:** Do not generate `UPDATE`, `DELETE`, or `INSERT` statements.
        - **Avoid `SELECT *`:** Only include the specific columns needed for the result.

        ---

        Generate a precise, efficient response. Clarity, accuracy, and safety are your top priorities.



        **Full Database Schema:**
        ```json
        {indented_schema}
        ```

        **Output Format:**

        Respond ONLY with a single, valid JSON object containing the analysis result. Do not include any explanations, greetings, or text outside the JSON structure.

        ```json
        {{
        "needs_sql": boolean, // true if a SQL query was generated, false otherwise
        "query": string | null, // The generated PostgreSQL query (string) if needs_sql is true, otherwise null
        "direct_answer": string | null // The direct natural language answer (string) if needs_sql is false, otherwise null
        }}
        ```

        **Examples:**

        *   **Example 1 (Needs SQL - Specific Item):**
            *   User Query: "Show me details for room 101"
            *   JSON Output:
                ```json
                {{
                "needs_sql": true,
                "query": "SELECT rd.room, rd.floor, rm.model_name, rd.description FROM room_data rd JOIN room_model rm ON rd.room_model_id = rm.id WHERE rd.room = '101' LIMIT 50;",
                "direct_answer": null
                }}
                ```
        *   **Example 2 (Doesn't Need SQL):**
            *   User Query: "Hello, who are you?"
            *   JSON Output:
                ```json
                {{
                "needs_sql": false,
                "query": null,
                "direct_answer": "I am PksBot, your AI assistant for hotel furniture installation information."
                }}
                ```
        *   **Example 3 (Needs SQL - Grouped Query):**
            *   User Query: "Which products are arriving this week?"
            *   JSON Output:
                ```json
                {{
                "needs_sql": true,
                "query": "SELECT pd.description, COUNT(pd.id) AS total_units, s.shipping_arrival FROM product_data pd JOIN product_room_model prm ON pd.id = prm.product_id JOIN room_model rm ON prm.room_model_id = rm.id JOIN room_data rd ON rm.id = rd.room_model_id JOIN schedule s ON rd.floor = s.floor WHERE s.shipping_arrival BETWEEN NOW() AND NOW() + INTERVAL '7 days' GROUP BY pd.description, s.shipping_arrival ORDER BY s.shipping_arrival ASC LIMIT 50;",
                "direct_answer": null
                }}
                ```
        *   **Example 4 (Needs SQL - Explicit Aggregation):**
            *   User Query: "How many chairs are in inventory?"
            *   JSON Output:
                ```json
                {{
                "needs_sql": true,
                "query": "SELECT SUM(inv.quantity_available) AS total_chairs FROM inventory inv JOIN product_data pd ON inv.client_id = pd.client_id WHERE pd.description ILIKE '%chair%' LIMIT 50;",
                "direct_answer": null
                }}
                ```

        **Generate the JSON response now based on the user query.**
"""


    user_prompt = f'**User Query:** "{user_message}"'

    return system_prompt.strip(), user_prompt.strip()

# New function for the Final Natural Language Response Prompt
def generate_natural_response_prompt(user_message, sql_query, rows):
    """Formats the prompt for the final LLM call to synthesize a natural response based on context and data."""

    data_summary = "No data was retrieved."
    columns = [] # Initialize columns
    data_preview = [] # Initialize data preview
    num_records = 0 # Initialize count

    if rows and isinstance(rows, dict):
        columns = rows.get('columns', []) # Assign within the check
        data = rows.get('rows')
        num_records = len(data) if isinstance(data, (list, tuple)) else 0

        if num_records > 0:
            max_rows_in_prompt = 10 # Slightly increase for context, still limited
            data_preview = data[:max_rows_in_prompt] # Assign within the check
            data_summary = f"Successfully retrieved {num_records} record(s)."
            data_summary += f"\\nColumns: {columns}"
            data_summary += f"\\nData Preview (first {len(data_preview)} rows): {str(data_preview)}"
            if num_records > max_rows_in_prompt:
                data_summary += f"\\n(Note: {num_records - max_rows_in_prompt} more rows exist but are not shown in this preview)"
        elif sql_query:
             data_summary = "The query executed successfully, but no matching records were found."
        elif not sql_query:
             data_summary = "No database query was performed for this request."

    elif sql_query:
         data_summary = "I attempted to retrieve information, but encountered an issue and could not fetch the data."

    system_prompt = f"""
    You are PksBot, a friendly and helpful AI assistant for a hotel furniture installation system.
    Your task is to provide a conversational and informative answer to the user's query based on the context provided.

    **Response Guidelines:**
    *   Aggregate data where applicable.
    *   Address the user's query directly and naturally.
    *   **If the user asks for a list of items (e.g., missing items, available products, room details) and data was retrieved (`num_records > 0`):**
        
        *   Present the results clearly using an HTML `<table>`.
        *   Use the `Columns` from the summary as table headers (`<thead><tr><th>...</th></tr></thead>`).
        *   Populate the table body (`<tbody>`) using the retrieved `Data Preview` (and mention if more rows exist).
        *   Include a brief introductory sentence before the table, like "Here are the items matching your request:"
    *   **For other types of queries OR if only one record was found:** Synthesize the key information from the 'Data Retrieval Summary' into a concise natural language sentence or paragraph. Explain what the data means.
    *   If no data was found (but the query was valid), state that clearly and politely (e.g., "I couldn't find any records matching your criteria.").
    *   If a query was attempted but failed, inform the user that you couldn't retrieve the information due to an issue (without technical details).
    *   If no database query was needed or attempted, just answer the user's original query directly.
    *   Keep the response concise and easy to understand.
    *   Do NOT include the raw SQL query in your response.
    *   Do NOT use markdown formatting (like ``` ```) around the HTML table if you generate one.
    *   Maintain a helpful and professional tone.
    

    **Generate the final natural language response for the user now.**

    
    """

    user_prompt = f"""  
    **Context:**
    1.  **User's Original Query:** "{user_message}"
    2.  **Database Query Attempted:** `{sql_query if sql_query else 'None'}`
    3.  **Data Retrieval Summary:** {data_summary}
    """
    return [
        {"role": "system", "content": system_prompt.strip()},
        {"role": "user", "content": user_prompt.strip()},
    ]
