import os
import getpass
from pydantic import BaseModel
from typing import Dict, TypedDict, List, Any
from langchain.chat_models import init_chat_model
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.tools import tool
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.checkpoint.memory import MemorySaver

# Import Custom Modules
import sts_util as stu

# Handle Environment Variables
if "GOOGLE_API_KEY" not in os.environ:
    os.environ["GOOGLE_API_KEY"] = getpass.getpass("Enter your Google API key: ")
if "LANGSMITH_API_KEY" not in os.environ:
    os.environ["LANGSMITH_API_KEY"] = getpass.getpass("Enter your Langsmith API key: ")
if "E2B_API_KEY" not in os.environ:
    os.environ["E2B_API_KEY"] = getpass.getpass("Enter your E2B API key: ")

# Create the Model
model = init_chat_model("gemini-2.0-flash", model_provider="google_genai", temperature=0.6)

# Define Custom State
class AgentState(TypedDict):
    task: str
    draft: str
    generate: str
    execute: str
    revision_number: int
    max_revisions: int
    generate_state: int
    session_state: any

class Queries(BaseModel):
    queries: List[str]

# Define the Coder Prompt
CODER_PROMPT = '''You are an expert Python programmer. You will receive coding problems similar to LeetCode questions, 
which may include problem statements, sample inputs, and examples. Your task is to:
    1. Analyze the problem carefully and Optimally with best possible time and space complexities.
    2. Write clean, efficient Python code to solve it
    3. Include proper documentation and type hints
    4. The code will be executed in an e2b sandbox environment
Please ensure your code is complete and handles edge cases appropriately.'''

# Create the Coder Node
def coder_node(state: AgentState):
    messages = [
        SystemMessage(content=CODER_PROMPT),
        HumanMessage(content=state['task'])
    ]
    response = model.invoke(messages)
    return {"draft": response.content}

# Define the Tool
@tool
def execute_python(session_state, code: str) -> Dict[str, Any]:
    """
    Help execute code in E2B
    """
    if not session_state.sandbox:
        stu.initialize_sandbox(session_state)
    
    execution = session_state.sandbox.run_code(code)
    return {
        "logs": execution.logs,
        "files": session_state.sandbox.files.list("/")
    }

# Define the Executer Prompt
EXECUTER_PROMPT = '''You are an expert at executing Python code in sandbox environments.
Your task is to:
    1. Take the provided Python code
    2. Use the tool to execute it in the e2b sandbox
    3. Only call the tool once.
'''

# Bind the Tool
tools = [execute_python]
model_with_tools = model.bind_tools(tools)

# Create the Executer Node
def executer_node(state: AgentState):
    messages = [
        SystemMessage(content=EXECUTER_PROMPT),
        HumanMessage(content=state['draft'])
    ]
    response = model_with_tools.invoke(messages)
    if "Execution Result" in response.content: 
        res_state = int(1)
    else:
        res_state = int(0)
    return {"revision_number": state['revision_number'] + 1}

# Define the Rectifier Prompt
RECTIFIER_PROMPT = '''You are an expert Python programmer. You will receive code for a particular problem, 
alongwith problem statements, sample inputs, examples and the errors or result upon execution 
of the code. Your task is to:
    1. Check if there are any errors except for sandbox timeout errors. If errors are present, Analyze the error carefully and correct the code to rectify the errors.
    2. If no errors are present, and sandbox is running, then do not revise the code.
    2. If error resolution is not possible, then rewrite clean, efficient Python code to solve the problem statement.
    3. Include proper documentation and type hints
    4. The code will be executed in an e2b sandbox environment
Please ensure your code is complete and handles edge cases appropriately.'''

# Create the Rectifier Node
def rectifier_node(state: AgentState):
    messages = [
        SystemMessage(content=RECTIFIER_PROMPT),
        HumanMessage(content=state['generate'])
    ]
    response = model.invoke(messages)
    return {"draft": response.content}

# Define the Conditional Function
def should_continue(state: AgentState):
    if state['revision_number'] > state['max_revisions'] or state['generate_state'] > int(0):
        return END
    return {"draft"}

# Build the Graph
builder = StateGraph(AgentState)

# Add Nodes
builder.add_node('coder', coder_node)
builder.add_node('executer', executer_node)
tool_node = ToolNode(tools)
builder.add_node("tools", tool_node)
builder.add_node('rectifier', rectifier_node)

# Set the Entry point
builder.set_entry_point('coder')

# Add the Edges
builder.add_conditional_edges(
    'executer',
    should_continue,
    {END: END, 'rectifier': 'rectifier'}
)
builder.add_conditional_edges('executer', tools_condition)
builder.add_edge('coder', 'executer')
builder.add_edge('tools', 'executer')
builder.add_edge('rectifier', 'executer')

# Add the Memory
memory = SqliteSaver.from_conn_string(':memory:')

# Compile the Graph
graph = builder.compile(checkpointer=MemorySaver())

# Format Results
def generate_result(gen_task: str, session_state):
    prompt = {
            'task': gen_task,
            'max_revisions': 2,
            'revision_number': 0,
            'generate_state': 0,
            'session_state': session_state
        }
    thread = {'configurable': {'thread_id': '1'}}
    response = graph.invoke(prompt, thread)

    res_key = "__end__"
    for res in response:
        if res_key in (res.content):
            result = str(res.content)
    idx = result.find(res_key)
    if idx != -1:
        final_response = result[idx + len(res_key):]
    return final_response