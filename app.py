from flask import Flask, request, jsonify, send_from_directory
from neo4j import GraphDatabase
import os
from dotenv import load_dotenv
import time

load_dotenv()

app = Flask(__name__)

# Neo4j connection details
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://neo4j:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "testpassword")

def init_database():
    """Initialize the database with schema and sample data"""
    try:
        with driver.session() as session:
            # First check if database is already initialized
            result = session.run("MATCH (n) RETURN count(n) as count")
            if result.single()['count'] > 0:
                print("Database already contains data, skipping initialization")
                return

            # Run database_setup.cypher
            print("Setting up database schema...")
            with open('setup/database_setup.cypher', 'r') as file:
                setup_queries = file.read().split(';')
                for query in setup_queries:
                    if query.strip():
                        session.run(query)
            
            # Run sample_data.cypher
            print("Loading sample data...")
            with open('setup/sample_data.cypher', 'r') as file:
                data_queries = file.read().split(';')
                for query in data_queries:
                    if query.strip():
                        try:
                            session.run(query)
                        except Exception as e:
                            print(f"Warning: Error executing query: {str(e)}")
                            continue
            
            print("Database initialized successfully")
    except Exception as e:
        print(f"Error initializing database: {str(e)}")
        raise e

def wait_for_neo4j():
    """Wait for Neo4j to be available"""
    max_retries = 30
    for i in range(max_retries):
        try:
            driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
            with driver.session() as session:
                session.run("RETURN 1")
            print("Successfully connected to Neo4j")
            return driver
        except Exception as e:
            print(f"Attempt {i+1}/{max_retries} to connect to Neo4j failed: {str(e)}")
            time.sleep(2)
    raise Exception("Could not connect to Neo4j")

def cleanup_database():
    """Clean up the database before initialization"""
    try:
        with driver.session() as session:
            # Remove all nodes and relationships
            session.run("MATCH (n) DETACH DELETE n")
            # Remove all constraints and indexes
            session.run("CALL apoc.schema.assert({},{})")
            print("Database cleaned up successfully")
    except Exception as e:
        print(f"Warning: Cleanup error: {str(e)}")

# Initialize Neo4j driver and database
driver = wait_for_neo4j()

# Only clean up if environment variable is set
if os.getenv('CLEAN_DB', 'false').lower() == 'true':
    cleanup_database()

init_database()

@app.route('/')
def index():
    return send_from_directory('static', 'index.html')

@app.route('/get_recipes')
def get_recipes():
    try:
        with driver.session() as session:
            query = """
            MATCH (r:Recipe)-[:CONTAINS]->(i:Ingredient)
            WITH r, collect(i.name) as ingredients
            RETURN 
                id(r) as id,
                r.name as name,
                r.instructions as instructions,
                r.calories as calories,
                r.time as time,
                r.difficulty as difficulty,
                r.cuisine as cuisine,
                ingredients
            ORDER BY r.name
            """
            result = session.run(query)
            recipes = [dict(record) for record in result]
            return jsonify(recipes), 200
    except Exception as e:
        print(f"Error getting recipes: {str(e)}")
        return jsonify({"error": str(e)}), 500

# Add other routes as needed...

if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True)
