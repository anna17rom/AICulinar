from flask import Flask, request, jsonify
from neo4j import GraphDatabase
import os

app = Flask(__name__)

# Neo4j connection details
NEO4J_URI = "bolt://localhost:7687"  # Update this if your Neo4j is not running locally
NEO4J_USER = "neo4j"  # Replace with your Neo4j username
NEO4J_PASSWORD = "saksuguan"  # Replace with your Neo4j password

# Initialize Neo4j driver
driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

@app.route('/')
def index():
    return app.send_static_file('index.html')

@app.route('/add_recipe', methods=['POST'])
def add_recipe():
    data = request.json
    
    with driver.session() as session:
        result = session.write_transaction(create_recipe, data['name'], data['ingredients'], data['instructions'])
    
    return jsonify({"message": "Recipe added successfully", "id": result}), 201

@app.route('/get_recipes', methods=['GET'])
def get_recipes():
    with driver.session() as session:
        recipes = session.read_transaction(get_all_recipes)
    
    return jsonify(recipes)

def create_recipe(tx, name, ingredients, instructions):
    query = (
        "CREATE (r:Recipe {name: $name, instructions: $instructions}) "
        "WITH r "
        "UNWIND $ingredients AS ingredient "
        "MERGE (i:Ingredient {name: ingredient}) "
        "CREATE (r)-[:CONTAINS]->(i) "
        "RETURN id(r) AS recipe_id"
    )
    result = tx.run(query, name=name, ingredients=ingredients.split(','), instructions=instructions)
    return result.single()["recipe_id"]

def get_all_recipes(tx):
    query = (
        "MATCH (r:Recipe)-[:CONTAINS]->(i:Ingredient) "
        "RETURN id(r) AS id, r.name AS name, r.instructions AS instructions, "
        "collect(i.name) AS ingredients"
    )
    result = tx.run(query)
    return [dict(record) for record in result]

@app.route('/test_connection')
def test_connection():
    try:
        with driver.session() as session:
            result = session.run("RETURN 'Connection successful' AS message")
            message = result.single()['message']
        return jsonify({"status": "success", "message": message}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/test_add_recipe')
def test_add_recipe():
    test_recipe = {
        "name": "Test Recipe",
        "ingredients": ["Ingredient 1", "Ingredient 2"],
        "instructions": "Test instructions"
    }
    try:
        with driver.session() as session:
            result = session.write_transaction(
                create_recipe, 
                test_recipe['name'], 
                test_recipe['ingredients'], 
                test_recipe['instructions']
            )
        return jsonify({"status": "success", "message": "Test recipe added", "id": result}), 201
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/test_get_recipes')
def test_get_recipes():
    try:
        with driver.session() as session:
            recipes = session.read_transaction(get_all_recipes)
        return jsonify({"status": "success", "recipes": recipes}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/setup_database')
def setup_database():
    try:
        with driver.session() as session:
            # Run database_setup.cypher
            with open('setup/database_setup.cypher', 'r') as file:
                setup_queries = file.read().split(';')
                for query in setup_queries:
                    if query.strip():  # Skip empty queries
                        session.run(query)
            
            # Run sample_data.cypher
            with open('setup/sample_data.cypher', 'r') as file:
                sample_data_queries = file.read().split(';')
                for query in sample_data_queries:
                    if query.strip():  # Skip empty queries
                        session.run(query)
            
        return jsonify({"status": "success", "message": "Database setup completed successfully"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)

