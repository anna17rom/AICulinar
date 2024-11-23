from flask import Flask, request, jsonify, send_from_directory, render_template
from neo4j import GraphDatabase
import os
from dotenv import load_dotenv
import time
import requests
from typing import List, Dict
from werkzeug.utils import secure_filename
import cloudinary
import cloudinary.uploader
import cloudinary.api
from flask_mail import Mail, Message
import uuid
from werkzeug.security import generate_password_hash, check_password_hash

load_dotenv()

app = Flask(__name__)

# Neo4j connection details
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://neo4j:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "testpassword")

# Spoonacular API details
SPOONACULAR_API_KEY = os.getenv("SPOONACULAR_API_KEY", "your_spoonacular_api_key")
SPOONACULAR_BASE_URL = "https://api.spoonacular.com/recipes"

# Add these configurations after creating the Flask app
UPLOAD_FOLDER = 'static/recipe_images'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Create upload folder if it doesn't exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Configure Cloudinary with your credentials
cloudinary.config(
    cloud_name='dwjzjoidh',  # Your Cloudinary cloud name
    api_key='415893377848277',  # Your Cloudinary API key
    api_secret='Plp-FDLQipVhCZFZI43TXxIc1Gc'  # Your Cloudinary API secret
)

# Configure Flask-Mail
app.config['MAIL_SERVER'] = 'smtp.example.com'  # Replace with your mail server
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'your_email@example.com'  # Your email
app.config['MAIL_PASSWORD'] = 'your_password'  # Your email password
app.config['MAIL_DEFAULT_SENDER'] = 'your_email@example.com'  # Default sender
mail = Mail(app)

# User database (for demonstration purposes, use a real database in production)
users = {}

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

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
                r.image_path as image_path,
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
                    r.cuisine = $cuisine,
                    r.image_path = $image_path
                WITH r
                UNWIND $ingredients as ingredient
                MERGE (i:Ingredient {name: toLower(trim(ingredient))})
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
                    "ingredients": [ing["name"] for ing in recipe["extendedIngredients"]],
                    "image_path": recipe.get("image", "")
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
        print("Received form data:", data)  # Debug log
        
        # Generate a unique recipe_id
        recipe_id = str(int(time.time()))
        
        # Handle image upload to Cloudinary
        image_path = None
        if 'image' in request.files:
            file = request.files['image']
            print("Received file:", file.filename if file else "No file")  # Debug log
            
            if file and file.filename and allowed_file(file.filename):
                # Upload to Cloudinary
                upload_result = cloudinary.uploader.upload(file)
                image_path = upload_result['secure_url']  # Get the URL of the uploaded image
                print(f"Image uploaded to Cloudinary: {image_path}")  # Debug log
            else:
                print("File not allowed or no file uploaded")  # Debug log
                return jsonify({"error": "File type not allowed or no file uploaded"}), 400
        
        with driver.session() as session:
            # Create Cypher query for the new recipe
            query = """
            CREATE (r:Recipe {
                recipe_id: $recipe_id,
                name: $name,
                instructions: $instructions,
                difficulty: 'medium',
                time: $time,
                calories: $calories,
                cuisine: 'Unknown',
                image_path: $image_path
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
            
            # Get optional fields with default values
            time_required = int(data.get('time', 30))
            calories = int(data.get('calories', 0))
            
            # Recipe data for the query
            recipe_data = {
                "recipe_id": recipe_id,
                "name": data.get('name'),
                "instructions": data.get('instructions'),
                "ingredients": ingredients_list,
                "image_path": image_path,  # This will be the Cloudinary URL
                "time": time_required,
                "calories": calories
            }
            
            print("Executing query with data:", recipe_data)  # Debug log
            session.run(query, recipe_data)
            
            return jsonify({
                "message": "Recipe added successfully",
                "recipe_id": recipe_id,
                "image_path": image_path  # This will be the Cloudinary URL
            }), 200
            
    except Exception as e:
        print(f"Error adding recipe: {str(e)}")
        return jsonify({"error": str(e)}), 500

# Add this new route
@app.route('/search_recipes')
def search_recipes():
    try:
        search_term = request.args.get('term', '').lower()
        cuisine = request.args.get('cuisine', '')
        difficulty = request.args.get('difficulty', '')
        
        with driver.session() as session:
            query = """
            MATCH (r:Recipe)-[:CONTAINS]->(i:Ingredient)
            WHERE toLower(r.name) CONTAINS $search_term
            OR toLower(i.name) CONTAINS $search_term
            OR toLower(r.instructions) CONTAINS $search_term
            WITH r, collect(i.name) as ingredients
            WHERE (size($cuisine) = 0 OR r.cuisine = $cuisine)
            AND (size($difficulty) = 0 OR r.difficulty = $difficulty)
            RETURN 
                id(r) as id,
                r.name as name,
                r.instructions as instructions,
                r.calories as calories,
                r.time as time,
                r.difficulty as difficulty,
                r.cuisine as cuisine,
                r.image_path as image_path,
                ingredients
            ORDER BY r.name
            """
            
            result = session.run(query, {
                "search_term": search_term,
                "cuisine": cuisine,
                "difficulty": difficulty
            })
            
            recipes = [dict(record) for record in result]
            return jsonify(recipes), 200
            
    except Exception as e:
        print(f"Error searching recipes: {str(e)}")
        return jsonify({"error": str(e)}), 500

# Route to serve images from the static folder (if necessary)
@app.route('/static/recipe_images/<filename>')
def serve_image(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/signup', methods=['POST'])
def signup():
    data = request.json
    name = data.get('name')
    email = data.get('email')
    password = data.get('password')

    # Check if the email already exists
    with driver.session() as session:
        existing_user = session.run("""
            MATCH (u:User {email: $email})
            RETURN u
        """, {"email": email}).single()

        if existing_user:
            return jsonify({"error": "Email already registered"}), 400

    # Create a unique verification token
    token = str(uuid.uuid4())

    # Store user in Neo4j
    try:
        with driver.session() as session:
            hashed_password = generate_password_hash(password)
            session.run("""
                CREATE (u:User {name: $name, email: $email, password: $hashed_password, verified: false, token: $token})
            """, {
                "name": name,
                "email": email,
                "hashed_password": hashed_password,
                "token": token
            })
    except Exception as e:
        return jsonify({"error": f"Failed to create user: {str(e)}"}), 500

    # Send verification email
    verification_link = f"http://localhost:5000/verify/{token}"
    msg = Message("Verify Your Email", recipients=[email])
    msg.body = f"Please click the link to verify your account: {verification_link}"
    mail.send(msg)

    return jsonify({"message": "Verification email sent"}), 200

@app.route('/verify/<token>', methods=['GET'])
def verify(token):
    try:
        with driver.session() as session:
            result = session.run("""
                MATCH (u:User {token: $token})
                SET u.verified = true
                RETURN u
            """, {"token": token})

            if result.single() is None:
                return jsonify({"error": "Invalid token"}), 400

            return jsonify({"message": "Account verified successfully"}), 200
    except Exception as e:
        return jsonify({"error": f"Verification failed: {str(e)}"}), 500

@app.route('/signin', methods=['POST'])
def signin():
    data = request.json
    email = data.get('email')
    password = data.get('password')

    # Check if the user exists and the password matches
    with driver.session() as session:
        user = session.run("""
            MATCH (u:User {email: $email})
            RETURN u
        """, {"email": email}).single()

        if not user:
            return jsonify({"error": "User not found"}), 404

        # Here you should compare the hashed password with the stored password
        if not check_password_hash(user['u']['password'], password):
            return jsonify({"error": "Invalid password"}), 401

    # Return success and a flag to indicate sign-in success
    return jsonify({"message": "Sign in successful", "signedIn": True}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True)

