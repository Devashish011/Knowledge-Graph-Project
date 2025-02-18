import requests
import json
import re
import pandas as pd
from neo4j import GraphDatabase

API_KEY = "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"

class Neo4jUploader:
    def __init__(self, uri, username, password, database):
        try:
            self.driver = GraphDatabase.driver(uri, auth=(username, password))
            self.database = database
            with self.driver.session(database=database) as session:
                session.run("RETURN 1")
            print("Connected to Neo4j")
        except Exception as e:
            print(f"Neo4j Connection Failed: {str(e)}")

    def close(self):
        self.driver.close()

    def execute_query(self, query, params=None):
        try:
            with self.driver.session(database=self.database) as session:
                session.run(query, params or {})
        except Exception as e:
            print(f"Error executing query: {query}\nError: {str(e)}")

def extract_json(response_text):
    match = re.search(r'```json\s*(\{.*\})\s*```', response_text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            print("Error parsing extracted JSON")
    return None

def get_relationships_from_llm(columns, sample_values):
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }

    prompt = f"""
        You are an expert in data modeling and transformation.  
        Analyze the given **CSV column names**: {columns}  
        and **first 5 rows**: {json.dumps(sample_values, indent=2)}.  

        Determine:  
        - Which columns should be **nodes (entities)**  
        - Which columns represent **relationships between nodes**  

        Generate **optimized Cypher queries** using `$rows` (bulk processing).  

        ### **Expected JSON Output (only valid JSON, no explanations):**  
        ```json
        {{
            "nodes": ["Movie", "Genre", "LeadStar", "Director", "MusicDirector"],  
            "relationships": [
                {{"start": "Movie", "end": "Genre", "type": "HAS_GENRE"}},
                {{"start": "Movie", "end": "LeadStar", "type": "STARRED_BY"}},
                {{"start": "Movie", "end": "Director", "type": "DIRECTED_BY"}},
                {{"start": "Movie", "end": "MusicDirector", "type": "MUSIC_BY"}}
            ],  
           "queries": {{
        "nodes": "UNWIND $rows AS row FOREACH (col IN ['Movie', 'Genre', 'LeadStar', 'Director', 'MusicDirector'] | MERGE (n:col {{name: row[col]}})))",
        "relationships": "UNWIND $rows AS row 
            MATCH (m:Movie {{name: row.`Movie Name`}})
            MATCH (g:Genre {{name: row.Genre}})
            MERGE (m)-[:HAS_GENRE]->(g)
            WITH m, row
            MATCH (ls:LeadStar {{name: row.`Lead Star`}})
            MERGE (m)-[:STARRED_BY]->(ls)
            WITH m, row
            MATCH (d:Director {{name: row.Director}})
            MERGE (m)-[:DIRECTED_BY]->(d)
            WITH m, row
            MATCH (md:MusicDirector {{name: row.`Music Director`}})
            MERGE (m)-[:MUSIC_BY]->(md)"
    }}
        }}
        ```
        **Return only valid JSON, no explanations.**
    """

    data = {
        "model": "google/gemini-2.0-flash-001",
        "messages": [{"role": "user", "content": prompt}]
    }

    response = requests.post(url, headers=headers, data=json.dumps(data))

    if response.status_code == 200:
        try:
            llm_response = response.json()
            if 'choices' in llm_response and 'message' in llm_response['choices'][0]:
                return extract_json(llm_response['choices'][0]['message']['content'])
            else:
                print("Unexpected response structure:", llm_response)
                return None
        except json.JSONDecodeError:
            print("Failed to decode JSON response")
            return None
    else:
        print(f"LLM API Error: {response.status_code}, {response.text}")
        return None


def format_label(label):
    return label.replace(" ", "_")

def format_relationship(rel):
    return rel.replace(" ", "_").upper()

def create_projected_graph(neo4j_uploader, graph_name):
    query = f"""
    CALL gds.graph.project(
        '{graph_name}',
        ['Movie', 'Genre', 'LeadStar', 'Director', 'MusicDirector'],
        [
            'HAS_GENRE',
            'STARRED_BY',
            'DIRECTED_BY',
            'MUSIC_BY'
        ]
    )
    """
    neo4j_uploader.execute_query(query)
    print(f"Projected graph '{graph_name}' created successfully!")



def process_csv_and_upload(csv_file, neo4j_uploader):
    df = pd.read_csv(csv_file)

    if df.empty:
        print("CSV file is empty!")
        return

    columns = list(df.columns)
    sample_values = df.head(5).to_dict(orient="records")

    llm_data = get_relationships_from_llm(columns, sample_values)
    if not llm_data:
        print("No valid response from LLM")
        return

    if 'nodes' not in llm_data or 'relationships' not in llm_data or 'queries' not in llm_data:
        print("Invalid structure in LLM response. Missing keys.")
        return

    # Corrected Cypher query for relationships
    corrected_relationships_query = """
    UNWIND $rows AS row 
    MATCH (m:Movie {name: row.`Movie Name`})
    MATCH (g:Genre {name: row.Genre})
    MERGE (m)-[:HAS_GENRE]->(g)
    WITH m, row
    MATCH (ls:LeadStar {name: row.`Lead Star`})
    MERGE (m)-[:STARRED_BY]->(ls)
    WITH m, row
    MATCH (d:Director {name: row.Director})
    MERGE (m)-[:DIRECTED_BY]->(d)
    WITH m, row
    MATCH (md:MusicDirector {name: row.`Music Director`})
    MERGE (m)-[:MUSIC_BY]->(md)
    """

    # Execute bulk queries for nodes and relationships
    params = {"rows": df.to_dict(orient="records")}

    neo4j_uploader.execute_query(llm_data["queries"]["nodes"], params)
    print(f"Nodes Created: {llm_data['nodes']}")

    neo4j_uploader.execute_query(corrected_relationships_query, params)
    print(f"Relationships Created: {llm_data['relationships']}")

    print("Upload Complete!")
    # Execute bulk queries for nodes and relationships
    params = {"rows": df.to_dict(orient="records")}

    neo4j_uploader.execute_query(llm_data["queries"]["nodes"], params)
    print(f"Nodes Created: {llm_data['nodes']}")

    neo4j_uploader.execute_query(llm_data["queries"]["relationships"], params)
    print(f"Relationships Created: {llm_data['relationships']}")

    create_projected_graph(neo4j_uploader, "movie_graph")
    print("Upload Complete!")



 

