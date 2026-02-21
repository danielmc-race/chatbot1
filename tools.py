from langchain_community.tools.tavily_search import TavilySearchResults

def get_tools():
    search_tool = TavilySearchResults(max_results=2)
    return [search_tool]
