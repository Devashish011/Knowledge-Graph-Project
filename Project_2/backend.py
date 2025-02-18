from flask import Flask, render_template, request, jsonify
from neo4j import GraphDatabase
from datetime import datetime
from neo4j.time import DateTime as Neo4jDateTime
import subprocess
import threading



app = Flask(__name__)
node_weights = {}

# Global Neo4j connection instance
neo4j_connector = None
graph_data_cache = {"nodes": [], "relationships": []}

def initialize_neo4j(uri, user, password, database_name):
    global neo4j_connector
    if neo4j_connector:
        neo4j_connector.close()  # Close the previous connection
    neo4j_connector = Neo4jConnector(uri, user, password, database_name)
def convert_datetime(obj):
    """ Recursively convert Neo4j DateTime objects to ISO strings. """
    if isinstance(obj, (datetime, Neo4jDateTime)):  # ✅ Convert Python and Neo4j DateTime
        return obj.isoformat()
    elif isinstance(obj, dict):  # ✅ Convert dictionary values
        return {k: convert_datetime(v) for k, v in obj.items()}
    elif isinstance(obj, list):  # ✅ Convert list elements
        return [convert_datetime(i) for i in obj]
    return obj  # Return other types as-is


def serialize_path(path):
    serialized = {
        "nodes": [
            {
                "id": node.element_id,
                "labels": list(node.labels),
                "properties": {k: (v.isoformat() if isinstance(v, datetime) else str(v)) for k, v in node.items()},
            }
            for node in path.nodes
        ],
        "relationships": [
            {
                "id": rel.element_id,
                "type": rel.type,
                "node1": rel.start_node.element_id,
                "node2": rel.end_node.element_id,
                "properties": {k: (v.isoformat() if isinstance(v, datetime) else str(v)) for k, v in rel.items()},
            }
            for rel in path.relationships
        ],
        "length": len(path.relationships),
    }
    print("Serialized Path:", serialized)  # Debugging
    return serialized



def run_query_with_timeout(session, query, params, timeout=10):
    result_container = {}

    def run_query():
        try:
            result_container["data"] = list(session.run(query, **params))
        except Exception as e:
            result_container["error"] = str(e)

    thread = threading.Thread(target=run_query)
    thread.start()
    thread.join(timeout)  # Wait for completion up to timeout

    if thread.is_alive():
        return {"error": "Query took too long!"}

    if "error" in result_container:
        return {"error": result_container["error"]}

    return result_container["data"]
# Neo4j driver setup
class Neo4jConnector:
    def __init__(self, uri, user, password,database_name):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))
        self.database_name = database_name

    def close(self):
        self.driver.close()
    
    def search_node(self, search_term):
        query = """
        MATCH (n)
        WHERE n.title CONTAINS $search OR n.name CONTAINS $search
        RETURN n 
        ORDER BY n.weight DESC
        LIMIT 1
        """
        with self.driver.session(database=self.database_name) as session:
            result = session.run(query, search=search_term)
            return result.single()
   

    def get_level_1_graph(self, node_id, limit=5, offset=0):
        query = """
        MATCH (n)-[r]-(m)
        WHERE id(n) = $node_id
        WITH DISTINCT n, r, m
        RETURN n, r, m
        ORDER BY COALESCE(m.weight, 0) DESC, m.timestamp DESC, id(m) ASC
        SKIP $offset LIMIT $limit
        """
        with self.driver.session(database=self.database_name) as session:
            result = session.run(query, node_id=node_id, offset=offset, limit=limit)
            
            nodes = {}
            relationships = []
            csv_files = set()

            for record in result:
                source_node = record["n"]
                target_node = record["m"]
                relationship = record["r"]
                
                if "csv_file" in source_node.keys():
                   if isinstance(source_node["csv_file"], list):
                       csv_files.update(source_node["csv_file"])  # Add all unique files
                   else:
                       csv_files.add(source_node["csv_file"])
                if "csv_file" in target_node.keys():
                    if isinstance(target_node["csv_file"], list):
                       csv_files.update(target_node["csv_file"])  # Add all unique files
                    else:
                       csv_files.add(target_node["csv_file"])
                    
                source_props = {k: convert_datetime(v) for k, v in source_node._properties.items()}
                target_props = {k: convert_datetime(v) for k, v in target_node._properties.items()}
                relationship_props = {k: convert_datetime(v) for k, v in relationship._properties.items()}

                # Add source and target nodes to the set
                if source_node.id not in nodes:
                    nodes[source_node.id] = {
                        "id": source_node.id,
                        "weight": source_node.get("weight", 0),
                        **source_props,  # Extract all properties
                    }

                if target_node.id not in nodes:
                    nodes[target_node.id] = {
                        "id": target_node.id,
                        "weight": target_node.get("weight", 0),
                        **target_props,  # Extract all properties
                    }

                # Add the relationship to the list
                relationships.append({
                    "source": source_node.id,
                    "target": target_node.id,
                    "type": relationship.type,
                    "properties": relationship_props 
                    
                })
            csv_query = """
            MATCH (n)
            WHERE n.csv_source IS NOT NULL
            RETURN DISTINCT n.csv_source AS csv_file
            """
            csv_result = session.run(csv_query)
            for record in csv_result:
                csv_files.add(record["csv_file"])
            print(csv_result)
            
            # Convert the set of nodes to a list
            nodes_list = sorted([{"id": node_id, **properties} for node_id, properties in nodes.items()],
            key=lambda x:x.get("weight",0),
            reverse=True)
            return {"nodes": nodes_list, "relationships": relationships, "csv_files": list(csv_files)}
            

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/search', methods=['POST'])
def search():
    search_term = request.json['query']
    limit = request.json.get('limit', 5)  # Get the limit from the frontend
    offset = request.json.get('offset', 0)
    if not neo4j_connector:
       return jsonify({"error": "Neo4j connection is not established."})# Get the offset from the frontend
    node = neo4j_connector.search_node(search_term)
    if not node:
        return jsonify({"error": "No matching node found"})
    node_id = node["n"].id
    graph_data = neo4j_connector.get_level_1_graph(node_id, limit=limit, offset=offset)
    graph_data = convert_datetime(graph_data)
    return jsonify(graph_data)
    
@app.route('/upload_csv', methods=['GET'])
def upload_csv():
    try:
        subprocess.Popen(["python", "Csv_neo_1.py"])  # Adjust filename if needed
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})
  
@app.route('/find_path', methods=['POST'])
def find_path():
    try:
        data = request.get_json()
        node1 = data.get("node1")
        node2 = data.get("node2")
        print(f"Received request: node1={node1}, node2={node2}")

        query = """
        MATCH (n1 {name: $node1}), (n2 {name: $node2})
        MATCH p = (n1)-[*..6]-(n2)  
        RETURN p ORDER BY length(p) ASC
        LIMIT 10
        """

        with neo4j_connector.driver.session() as session:
            results = session.run(query, node1=node1, node2=node2)
            paths = [serialize_path(record["p"]) for record in results]
            
        print(f"Query Results: {paths}")
        return jsonify({"paths": paths})

    except Exception as e:
        print(f"Error: {str(e)}")  
        return jsonify({"error": str(e)}), 500




    

@app.route('/update_weight', methods=['POST'])
def update_weight():
    data = request.json
    node_id = data.get('node_id')
    weight = data.get('weight')
    database_name = data.get('database_name')
    if not neo4j_connector:
        return jsonify({"error": "Neo4j connection is not established."})

    query = """
    MATCH (n)
    WHERE id(n) = $node_id
    SET n.weight = $weight
    RETURN n
    """
    with neo4j_connector.driver.session(database=database_name) as session:
        result = session.run(query, node_id=int(node_id), weight=weight)
        if result.single():
            return jsonify({"success": True})
        return jsonify({"success": False, "error": "Failed to update weight."})

@app.route('/explore_node', methods=['POST'])
def explore_node():
    data = request.json
    node_id = data.get('node_id')

    if not node_id:
        return jsonify({'error': 'Node ID is required'}), 400

    query = """
    MATCH (n)-[r]-(m) 
    WHERE ID(n) = $node_id 
    RETURN n, r, m
    """
    
    try:
        with neo4j_connector.driver.session() as session:
            results = session.run(query, node_id=int(node_id))  
            
            nodes = {}
            relationships = []
            
            for record in results:
                node1 = record["n"]
                node2 = record["m"]
                rel = record["r"]

                # Store unique nodes
                for node in [node1, node2]:
                    node_id = str(node.id)
                    if node_id not in nodes:
                        nodes[node_id] = {
                            "id": node_id,
                            "label": node["name"] if "name" in node else f"Node {node_id}",
                            "weight": node.get("weight", 0),
                            **node
                        }

                # Store relationships
                relationships.append({
                    "source": str(node1.id),
                    "target": str(node2.id),
                    "type": rel.type
                })
        
        return jsonify({"nodes": list(nodes.values()), "relationships": relationships})
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500


    
@app.route('/update_credentials', methods=['POST'])
def update_credentials():
    data = request.json
    new_uri = data.get('uri')
    new_username = data.get('username')
    new_password = data.get('password')
    new_database = data.get('database')

    if not new_uri or not new_username or not new_password or not new_database:
        return jsonify({"error": "Missing required credentials."})

    try:
        initialize_neo4j(new_uri, new_username, new_password, new_database)
        return jsonify({"success": True, "message": "Neo4j connection updated successfully."})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

if __name__ == "__main__":
    initialize_neo4j("bolt://localhost:7687", "neo4j", "12345678", "neo4j")
    app.run(debug=True,port=5001)
  
