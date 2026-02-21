import os
from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
from typing import Annotated
from langchain_groq import ChatGroq
from langchain_community.tools.tavily_search import TavilySearchResults
from langchain_core.messages import AnyMessage, SystemMessage, AIMessage
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.checkpoint.postgres import PostgresSaver
from langchain_core.messages import ToolMessage
from typing_extensions import TypedDict
from psycopg_pool import ConnectionPool
import uuid

# Cargar variables de entorno
load_dotenv()

# --- Flask App ---
app = Flask(__name__)
CORS(app)

# --- Pool de conexiones PostgreSQL ---
POSTGRES_URI = os.getenv("POSTGRES_URI")
connection_pool = ConnectionPool(POSTGRES_URI, min_size=1, max_size=10)


# --- Estado del agente ---
class AgentState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]


# --- Herramienta de búsqueda ---
search_tool = TavilySearchResults(max_results=2)
tools = [search_tool]

# --- Modelo LLM ---
llm = ChatGroq(model="llama-3.3-70b-versatile", temperature=0)
llm_con_tools = llm.bind_tools(tools)


# --- Nodos ---
def nodo_agente(state: AgentState):
    system = SystemMessage(
        content="Eres un asistente útil. Usa la búsqueda web cuando necesites información actualizada.")
    respuesta = llm_con_tools.invoke([system] + state["messages"])
    return {"messages": [respuesta]}


def nodo_herramientas(state: AgentState):
    ultimo_mensaje = state["messages"][-1]
    resultados = []
    for tool_call in ultimo_mensaje.tool_calls:
        tool = {tool.name: tool for tool in tools}[tool_call["name"]]
        resultado = tool.invoke(tool_call["args"])
        resultados.append(ToolMessage(content=str(resultado), tool_call_id=tool_call["id"]))
    return {"messages": resultados}


# --- Router ---
def debe_continuar(state: AgentState) -> str:
    ultimo_mensaje = state["messages"][-1]
    if isinstance(ultimo_mensaje, AIMessage) and hasattr(ultimo_mensaje, "tool_calls") and ultimo_mensaje.tool_calls:
        return "herramientas"
    return END


# --- Construir grafo ---
graph = StateGraph(AgentState)
graph.add_node("agente", nodo_agente)
graph.add_node("herramientas", nodo_herramientas)
graph.add_edge(START, "agente")
graph.add_conditional_edges("agente", debe_continuar, {"herramientas": "herramientas", END: END})
graph.add_edge("herramientas", "agente")

# --- Compilar agente con memoria ---
checkpointer = PostgresSaver(connection_pool)
agent = graph.compile(checkpointer=checkpointer)


@app.route('/health', methods=['GET'])
def health():
    """Endpoint para verificar que la API está funcionando"""
    return jsonify({"status": "ok"})


@app.route('/chat', methods=['POST'])
def chat():
    """Endpoint para enviar mensajes al chatbot"""
    data = request.json
    message = data.get('message')
    thread_id = data.get('thread_id', str(uuid.uuid4()))

    if not message:
        return jsonify({"error": "Message is required"}), 400

    try:
        config = {"configurable": {"thread_id": thread_id}}
        response = agent.invoke({"messages": [("user", message)]}, config)
        return jsonify({
            "response": response["messages"][-1].content,
            "thread_id": thread_id
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)