from langgraph.graph import StateGraph, END
from state import DependencyState
from nodes import changelog_node, route_after_changelog, diff_fallback_node


def build_graph():
    graph = StateGraph(DependencyState)

    graph.add_node("changelog", changelog_node)
    graph.add_node("diff_fallback", diff_fallback_node)

    graph.set_entry_point("changelog")

    graph.add_conditional_edges(
        "changelog",
        route_after_changelog,
        {
            "trustworthy": END,
            "needs_fallback": "diff_fallback",
        },
    )

    graph.add_edge("diff_fallback", END)

    return graph.compile()