#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
import networkx as nx


def execution_graph_to_nx_graph(execution_graph):
    G = nx.DiGraph()

    # Add nodes (with attributes if needed)
    for node in execution_graph["nodes"]:
        G.add_node(node["node_id"], **{k: v for k, v in node.items() if k != "node_id"})
    # Add edges
    for edge in execution_graph["edges"]:
        G.add_edge(edge["source"], edge["target"])
    return G


def nx_graph_to_dict(g):
    """
    Convert a networkx Graph to a dictionary with 'nodes' and 'edges' keys.
    Each node is a dict with at least 'node_id', plus any attributes.
    Each edge is a dict with 'source' and 'target'.
    """
    nodes = []
    for n, attrs in g.nodes(data=True):
        node_dict = {"node_id": str(n)}
        node_dict.update(attrs)
        nodes.append(node_dict)
    edges = []
    for u, v in g.edges():
        edges.append({"source": str(u), "target": str(v)})
    return {"nodes": nodes, "edges": edges}
