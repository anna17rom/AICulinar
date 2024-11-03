from flask import Flask, request, jsonify, send_from_directory
from neo4j import GraphDatabase
import os
from dotenv import load_dotenv
import time
import requests
from typing import List, Dict

load_dotenv()

app = Flask(__name__)

# Neo4j connection details
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://neo4j:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "testpassword")

# Spoonacular API details
SPOONACULAR_API_KEY = os.getenv("SPOONACULAR_API_KEY", "71e0ef0aa4c24ccc8cd0bec39181c81f")
SPOONACULAR_BASE_URL = "https://api.spoonacular.com/recipes"

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

def import_recipes_from_spoonacular(limit: int = 100):
    """Import recipes from Spoonacular API"""
    try:
        # Get random recipes from Spoonacular
        params = {
            "apiKey": SPOONACULAR_API_KEY,
            "number": limit,
            "addRecipeInformation": True,
        }
        response = requests.get(f"{SPOONACULAR_BASE_URL}/random", params=params)
        recipes = response.json()["recipes"]

        with driver.session() as session:
            for recipe in recipes:
                # Create Cypher query for each recipe
                query = """
                MERGE (r:Recipe {recipe_id: $recipe_id})
                SET r.name = $name,
                    r.instructions = $instructions,
                    r.calories = $calories,
                    r.time = $time,
                    r.difficulty = 'medium',
                    r.cuisine = $cuisine
                WITH r
                UNWIND $ingredients as ingredient
                MERGE (i:Ingredient {name: ingredient})
                MERGE (r)-[:CONTAINS]->(i)
                """
                
                # Extract recipe data
                recipe_data = {
                    "recipe_id": str(recipe["id"]),
                    "name": recipe["title"],
                    "instructions": recipe["instructions"],
                    "calories": recipe.get("nutrition", {}).get("nutrients", [{}])[0].get("amount", 0),
                    "time": recipe["readyInMinutes"],
                    "cuisine": recipe.get("cuisines", ["Unknown"])[0] if recipe.get("cuisines") else "Unknown",
                    "ingredients": [ing["name"] for ing in recipe["extendedIngredients"]]
                }
                
                session.run(query, recipe_data)
        
        return True
    except Exception as e:
        print(f"Error importing recipes: {str(e)}")
        return False

@app.route('/import_recipes', methods=['POST'])
def import_recipes():
    try:
        limit = request.json.get('limit', 100)
        success = import_recipes_from_spoonacular(limit)
        if success:
            return jsonify({"message": f"Successfully imported recipes"}), 200
        return jsonify({"error": "Failed to import recipes"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Add this new route after your other routes
@app.route('/add_recipe', methods=['POST'])
def add_recipe():
    try:
        data = request.form
        
        # Generate a unique recipe_id (you can modify this logic if needed)
        recipe_id = str(int(time.time()))
        
        with driver.session() as session:
            # Create Cypher query for the new recipe
            query = """
            CREATE (r:Recipe {
                recipe_id: $recipe_id,
                name: $name,
                instructions: $instructions,
                difficulty: 'medium',
                time: 30,
                calories: 0
            })
            WITH r
            UNWIND $ingredients as ingredient
            MERGE (i:Ingredient {name: toLower(trim(ingredient))})
            MERGE (r)-[:CONTAINS]->(i)
            RETURN r
            """
            
            # Parse ingredients from the comma or newline separated string
            ingredients_text = data.get('ingredients', '')
            ingredients_list = [
                ing.strip() 
                for ing in ingredients_text.replace('\n', ',').split(',')
                if ing.strip()
            ]
            
            # Recipe data for the query
            recipe_data = {
                "recipe_id": recipe_id,
                "name": data.get('name'),
                "instructions": data.get('instructions'),
                "ingredients": ingredients_list
            }
            
            # Execute the query
            session.run(query, recipe_data)
            
            return jsonify({"message": "Recipe added successfully"}), 200
            
    except Exception as e:
        print(f"Error adding recipe: {str(e)}")
        return jsonify({"error": str(e)}), 500

# Add other routes as needed...

if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True)
