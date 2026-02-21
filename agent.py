from typing import Annotated
from langchain_groq import ChatGroq
from langchain_core.messages import AnyMessage, SystemMessage, AIMessage, ToolMessage
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.checkpoint.postgres import PostgresSaver
from typing_extensions import TypedDict
from tools import get_tools


class AgentState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]


def create_agent(connection_pool):
    tools = get_tools()

    llm = ChatGroq(model="llama-3.3-70b-versatile", temperature=0)
    llm_con_tools = llm.bind_tools(tools)

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

    def debe_continuar(state: AgentState) -> str:
        ultimo_mensaje = state["messages"][-1]
        if isinstance(ultimo_mensaje, AIMessage) and hasattr(ultimo_mensaje,
                                                             "tool_calls") and ultimo_mensaje.tool_calls:
            return "herramientas"
        return END

    graph = StateGraph(AgentState)
    graph.add_node("agente", nodo_agente)
    graph.add_node("herramientas", nodo_herramientas)
    graph.add_edge(START, "agente")
    graph.add_conditional_edges("agente", debe_continuar, {"herramientas": "herramientas", END: END})
    graph.add_edge("herramientas", "agente")

    checkpointer = PostgresSaver(connection_pool)
    return graph.compile(checkpointer=checkpointer)
