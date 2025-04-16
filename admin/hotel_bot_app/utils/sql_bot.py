from langchain_core.prompts import ChatPromptTemplate
from langchain_community.utilities import SQLDatabase
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough
from langchain_openai import ChatOpenAI

# Setup DB connection
db_uri = "pass"
db = SQLDatabase.from_uri(db_uri)

# Define prompt template
template = """
Based on the table schema below, write a SQL query that would answer the user's question:
{schema}

Question: {question}
SQL Query:
"""
prompt = ChatPromptTemplate.from_template(template)

# Get schema from the DB
def get_schema(input_dict):
    return {"schema": db.get_table_info()}

# Setup LLM
llm = ChatOpenAI(api_key="pass")  # Replace with your actual key

# Build chain
sql_chain = (
    RunnablePassthrough.assign(schema=get_schema)
    | prompt
    | llm.bind(stop="\nSQL Results:")
    | StrOutputParser()
)

# Invoke chain
result = sql_chain.invoke({"question": "Can I get an install kit checklist for Room king size?"})
print(result)
final = db.run(result)
print(final)

# def run_query(query):
#     return db.run(query)
# template = """
#     Based on the table schema below, question, sql query, and sql response, write a natural language response:
#     {schema}
#     Question: {question}
#     SQL Query: {query}
#     SQL Response: {response}
#     """
# prompt = ChatPromptTemplate.from_template(template)

# full_chain = (
#     RunnablePassthrough.assign(query=sql_chain).assign(
#         schema=get_schema,
#         response= lambda variable: run_query(variable["query"])
#     )
#     | prompt
#     | llm  
# )

# full_chain.invoke({"question": "Can I get an install kit checklist for Room king size?"})
