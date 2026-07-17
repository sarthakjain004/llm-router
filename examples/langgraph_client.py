"""Point a LangChain / LangGraph app at the llm-router proxy.

The proxy is fully OpenAI-compatible, so you use ChatOpenAI with base_url set to
the proxy and the model set to a semantic alias. Failover, cooldowns, and
provider selection all happen server-side — your agent code never changes when
you add or reorder providers.

    pip install langchain-openai langgraph
    LITELLM_MASTER_KEY=sk-... python examples/langgraph_client.py
"""
import os

from langchain_openai import ChatOpenAI

PROXY_URL = os.environ.get("LLM_ROUTER_URL", "http://127.0.0.1:4000/v1")
MASTER_KEY = os.environ["LITELLM_MASTER_KEY"]  # the proxy's LITELLM_MASTER_KEY

# `model` is a semantic alias defined in config.yaml. Use these three:
#   agent-default  — general work; full failover chain (Gemini -> Groq -> ...)
#   vision         — image inputs
#   long-context   — very large prompts
llm = ChatOpenAI(
    base_url=PROXY_URL,
    api_key=MASTER_KEY,
    model="agent-default",
    temperature=0,
    timeout=120,
    max_retries=0,   # the proxy already retries + fails over; don't double up
)


def demo_stream() -> None:
    print("stream> ", end="", flush=True)
    for chunk in llm.stream("Say hello in exactly five words."):
        print(chunk.content, end="", flush=True)
    print()


def demo_tools() -> None:
    def get_weather(city: str) -> str:
        """Get the current weather for a city."""
        return f"It's sunny in {city}."

    agent = llm.bind_tools([get_weather])
    msg = agent.invoke("What's the weather in Paris? Use the tool.")
    print("tool_calls>", msg.tool_calls)


# --- Minimal LangGraph ReAct agent (uncomment if langgraph is installed) -------
# from langgraph.prebuilt import create_react_agent
#
# def demo_langgraph() -> None:
#     def get_weather(city: str) -> str:
#         """Get the current weather for a city."""
#         return f"It's sunny in {city}."
#     graph = create_react_agent(llm, tools=[get_weather])
#     out = graph.invoke({"messages": [("user", "Weather in Paris?")]})
#     print(out["messages"][-1].content)


if __name__ == "__main__":
    demo_stream()
    demo_tools()
    # demo_langgraph()
