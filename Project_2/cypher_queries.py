def create_nodes_query(node_labels):
    """
    Generates a Cypher query to create nodes based on the given labels.
    """
    query = """
    UNWIND $rows AS row
    FOREACH (col IN $node_labels | 
        FOREACH (ignore IN CASE WHEN row[col] IS NOT NULL THEN [1] ELSE [] END |
            MERGE (n:col {name: row[col]})
        )
    )
    """
    return query

def create_relationships_query(relationships):
    """
    Generates a Cypher query to create relationships based on the given relationships.
    """
    query = """
    UNWIND $rows AS row
    """
    for rel in relationships:
        start_node = rel["start"]
        end_node = rel["end"]
        rel_type = rel["type"]
        query += f"""
        MATCH (a:{start_node} {{name: row.`{start_node}`}})
        MATCH (b:{end_node} {{name: row.`{end_node}`}})
        MERGE (a)-[:{rel_type}]->(b)
        WITH row  // Add WITH clause to separate MERGE and MATCH
        """
    # Remove the final WITH clause
    query = query.rstrip("WITH row  // Add WITH clause to separate MERGE and MATCH\n")
    return query



# def find_missing_links_query(node_labels, relationships):
#     """
#     Generates a Cypher query to find missing links based on common neighbors.
#     """
#     # Extract relationship types from the relationships list
#     relationship_types = [rel["type"] for rel in relationships]

#     query = f"""
#     MATCH (node1)-[:{relationship_types[0]}]->(common)<-[:{relationship_types[0]}]-(node2)
#     WHERE node1 <> node2 AND NOT (node1)--(node2)
#     WITH node1, node2, collect(common) AS common_neighbors, count(common) AS common_neighbor_count
#     RETURN node1.name AS node1, node2.name AS node2, common_neighbor_count, [n IN common_neighbors | n.name] AS common_neighbor_names
#     ORDER BY common_neighbor_count DESC
#     LIMIT 5
#     """
#     return query