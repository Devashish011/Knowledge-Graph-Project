# def create_projected_graph(neo4j_uploader, nodes, relationships):
#     """
#     Create a projected graph in Neo4j dynamically.
#     """
#     print(f"Creating projected graph for nodes: {nodes} and relationships: {relationships}")

#     node_labels = [node.capitalize() for node in nodes]  # Capitalize node labels

#     # Fix relationship projection to Cypher List format
#     relationship_types = [f'"{rel["type"]}"' for rel in relationships]

#     # Create projection query
#     projection_query = f"""
#     CALL gds.graph.project(
#         'projectedGraph',
#         {node_labels},
#         {relationship_types}
#     )
#     """
    
#     print(f"Executing projection query:\n{projection_query}")
#     neo4j_uploader.execute_query(projection_query)
#     print("Projected Graph Creation Completed!")
