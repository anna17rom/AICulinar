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
import tensorflow as tf
import json
from PIL import Image
import numpy as np

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
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

# Configure Cloudinary with your credentials
cloudinary.config(
    cloud_name='dwjzjoidh',  # Your Cloudinary cloud name
    api_key='415893377848277',  # Your Cloudinary API key
    api_secret='Plp-FDLQipVhCZFZI43TXxIc1Gc'  # Your Cloudinary API secret
)

# Configure Flask-Mail
app.config['MAIL_SERVER'] = os.getenv('MAIL_SERVER', 'smtp.gmail.com')
app.config['MAIL_PORT'] = int(os.getenv('MAIL_PORT', 587))
app.config['MAIL_USE_TLS'] = os.getenv('MAIL_USE_TLS', 'True').lower() == 'true'
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = os.getenv('MAIL_USERNAME')
mail = Mail(app)

# User database (for demonstration purposes, use a real database in production)
users = {}

# Load your model
model = tf.keras.models.load_model('product_model.h5')

# Load class names
with open('model_classes.json', 'r') as f:
    class_names = json.load(f)

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
            result = session.run("""
                MATCH (r:Recipe)-[:CONTAINS]->(i:Ingredient)
                WITH r, collect(i.name) as ingredients
                RETURN 
                    r.recipe_id as recipe_id,
                    r.name as name,
                    r.instructions as instructions,
                    r.calories as calories,
                    r.time as time,
                    r.difficulty as difficulty,
                    r.cuisine as cuisine,
                    r.image_path as image_path,
                    ingredients
            """)
            recipes = [dict(record) for record in result]
            return jsonify(recipes), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

def import_recipes_from_spoonacular(limit: int = 100):
    """Import recipes from Spoonacular API"""
    try:
        # Add debug logging
        print(f"Starting recipe import with API key: {SPOONACULAR_API_KEY}")
        
        # Get random recipes from Spoonacular
        params = {
            "apiKey": SPOONACULAR_API_KEY,
            "number": limit,
            "addRecipeInformation": True,
        }
        print(f"Requesting recipes from Spoonacular with params: {params}")
        
        response = requests.get(f"{SPOONACULAR_BASE_URL}/random", params=params)
        print(f"Spoonacular response status: {response.status_code}")
        
        if response.status_code != 200:
            print(f"Error response from Spoonacular: {response.text}")
            return False
            
        recipes = response.json()["recipes"]
        print(f"Retrieved {len(recipes)} recipes from Spoonacular")
        
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
        user_email = data.get('user_email')
        
        if not user_email:
            return jsonify({"error": "User email is required"}), 400
        
        # Generate a unique recipe_id
        recipe_id = str(int(time.time()))
        
        # Handle image upload to Cloudinary
        image_path = None
        if 'image' in request.files:
            file = request.files['image']
            if file and file.filename and allowed_file(file.filename):
                upload_result = cloudinary.uploader.upload(file)
                image_path = upload_result['secure_url']
        
        with driver.session() as session:
            # First verify the user exists
            user_check = session.run("""
                MATCH (u:User {email: $email})
                RETURN u
            """, {"email": user_email}).single()
            
            if not user_check:
                return jsonify({"error": "User not found"}), 404

            # Parse ingredients
            ingredients_text = data.get('ingredients', '')
            ingredients_list = [
                ing.strip() 
                for ing in ingredients_text.replace('\n', ',').split(',')
                if ing.strip()
            ]
            
            # Create recipe and relationships
            result = session.run("""
                CREATE (r:Recipe {
                    recipe_id: $recipe_id,
                    name: $name,
                    instructions: $instructions,
                    difficulty: 'medium',
                    time: $time,
                    calories: $calories,
                    cuisine: $cuisine,
                    image_path: $image_path
                })
                WITH r
                MATCH (u:User {email: $user_email})
                CREATE (u)-[:ADDED_RECIPE]->(r)
                WITH r
                UNWIND $ingredients as ingredient
                MERGE (i:Ingredient {name: toLower(trim(ingredient))})
                CREATE (r)-[:CONTAINS]->(i)
                RETURN r
            """, {
                "recipe_id": recipe_id,
                "name": data.get('name'),
                "instructions": data.get('instructions'),
                "ingredients": ingredients_list,
                "image_path": image_path,
                "time": int(data.get('time', 30)),
                "calories": int(data.get('calories', 0)),
                "cuisine": data.get('cuisine', 'Unknown'),
                "user_email": user_email
            })
            
            if result.single():
                return jsonify({
                    "message": "Recipe added successfully",
                    "recipe_id": recipe_id,
                    "image_path": image_path
                }), 200
            else:
                return jsonify({"error": "Failed to create recipe"}), 500
            
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

@app.route('/signup', methods=['POST'])
def signup():
    data = request.json
    name = data.get('name')
    email = data.get('email')
    password = data.get('password')

    # Input validation
    if not all([name, email, password]):
        return jsonify({"error": "All fields are required"}), 400

    # Check if the email already exists
    try:
        with driver.session() as session:
            existing_user = session.run("""
                MATCH (u:User {email: $email})
                RETURN u
            """, {"email": email}).single()

            if existing_user:
                return jsonify({"error": "Email already registered"}), 400

            # Create a unique verification token
            token = str(uuid.uuid4())
            
            # Create user with proper Cypher syntax
            result = session.run("""
                CREATE (u:User {
                    name: $name,
                    email: $email,
                    password: $password,
                    verified: true,
                    token: $token
                })
                RETURN u
            """, {
                "name": name,
                "email": email,
                "password": generate_password_hash(password),
                "token": token
            })

            # Verify the user was created
            if result.single():
                return jsonify({
                    "message": "User registered successfully",
                    "success": True
                }), 200
            else:
                return jsonify({"error": "Failed to create user"}), 500

    except Exception as e:
        print(f"Signup error: {str(e)}")  # Add debug logging
        return jsonify({"error": str(e)}), 500

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

# Add these new routes
@app.route('/like_recipe/<recipe_id>', methods=['POST'])
def like_recipe(recipe_id):
    try:
        data = request.json
        user_email = data.get('user_email')

        with driver.session() as session:
            # First verify the recipe exists
            recipe_check = session.run("""
                MATCH (r:Recipe {recipe_id: $recipe_id})
                RETURN r
            """, {"recipe_id": recipe_id}).single()
            
            if not recipe_check:
                return jsonify({"error": "Recipe not found"}), 404

            result = session.run("""
                MATCH (u:User {email: $email})
                MATCH (r:Recipe {recipe_id: $recipe_id})
                MERGE (u)-[l:LIKED]->(r)
                RETURN r.name as recipe_name
            """, {"email": user_email, "recipe_id": recipe_id})
            
            record = result.single()
            if record:
                return jsonify({"message": f"Recipe '{record['recipe_name']}' liked successfully"}), 200
            return jsonify({"error": "User not found"}), 404

    except Exception as e:
        print(f"Error liking recipe: {str(e)}")  # Add debug logging
        return jsonify({"error": str(e)}), 500

@app.route('/want_to_try_recipe/<recipe_id>', methods=['POST'])
def want_to_try_recipe(recipe_id):
    try:
        data = request.json
        user_email = data.get('user_email')

        with driver.session() as session:
            # First, check if the relationship already exists
            check_result = session.run("""
                MATCH (u:User {email: $email})-[w:WANTS_TO_TRY]->(r:Recipe {recipe_id: $recipe_id})
                RETURN w
            """, {"email": user_email, "recipe_id": recipe_id})
            
            if check_result.single():
                return jsonify({"message": "Recipe already in Want to Try list"}), 200

            # If not, create the relationship
            result = session.run("""
                MATCH (u:User {email: $email})
                MATCH (r:Recipe {recipe_id: $recipe_id})
                MERGE (u)-[w:WANTS_TO_TRY]->(r)
                RETURN r.name as recipe_name
            """, {"email": user_email, "recipe_id": recipe_id})
            
            record = result.single()
            if record:
                return jsonify({"message": f"Recipe '{record['recipe_name']}' added to Want to Try list"}), 200
            return jsonify({"error": "Recipe or user not found"}), 404

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/get_user_recipes/<type>')
def get_user_recipes(type):
    try:
        user_email = request.args.get('user_email')
        if not user_email:
            return jsonify({"error": "User email is required"}), 400

        # Map the type parameter to the correct relationship type
        relationship_map = {
            'liked': 'LIKED',
            'cooked': 'COOKED',
            'want_to_try': 'WANTS_TO_TRY',
            'added': 'ADDED_RECIPE'
        }
        
        relationship_type = relationship_map.get(type)
        if not relationship_type:
            return jsonify({"error": "Invalid recipe type"}), 400

        with driver.session() as session:
            result = session.run("""
                MATCH (u:User {email: $email})-[:""" + relationship_type + """]->(r:Recipe)
                OPTIONAL MATCH (r)-[:CONTAINS]->(i:Ingredient)
                WITH r, collect(DISTINCT i.name) as ingredients
                RETURN 
                    r.recipe_id as recipe_id,
                    r.name as name,
                    r.instructions as instructions,
                    r.image_path as image_path,
                    r.cuisine as cuisine,
                    r.difficulty as difficulty,
                    r.time as time,
                    r.calories as calories,
                    ingredients
            """, {"email": user_email})
            
            recipes = [dict(record) for record in result]
            print(f"Found {len(recipes)} {type} recipes for user {user_email}")  # Debug log
            return jsonify(recipes), 200

    except Exception as e:
        print(f"Error getting {type} recipes: {str(e)}")  # Debug log
        return jsonify({"error": str(e)}), 500

@app.route('/cooked_recipe/<recipe_id>', methods=['POST'])
def cooked_recipe(recipe_id):
    try:
        data = request.json
        user_email = data.get('user_email')

        with driver.session() as session:
            # First verify the recipe exists
            recipe_check = session.run("""
                MATCH (r:Recipe {recipe_id: $recipe_id})
                RETURN r
            """, {"recipe_id": recipe_id}).single()
            
            if not recipe_check:
                return jsonify({"error": "Recipe not found"}), 404

            result = session.run("""
                MATCH (u:User {email: $email})
                MATCH (r:Recipe {recipe_id: $recipe_id})
                MERGE (u)-[c:COOKED]->(r)
                RETURN r.name as recipe_name
            """, {"email": user_email, "recipe_id": recipe_id})
            
            record = result.single()
            if record:
                return jsonify({"message": f"Recipe '{record['recipe_name']}' marked as cooked"}), 200
            return jsonify({"error": "User not found"}), 404

    except Exception as e:
        print(f"Error marking recipe as cooked: {str(e)}")  # Add debug logging
        return jsonify({"error": str(e)}), 500



@app.route('/get_user_profile')
def get_user_profile():
    try:
        user_email = request.args.get('user_email')
        
        with driver.session() as session:
            result = session.run("""
                MATCH (u:User {email: $email})
                RETURN u.name as name,
                       u.age as age,
                       u.height as height,
                       u.weight as weight,
                       u.goal as goal
            """, {"email": user_email})
            
            user_data = result.single()
            if user_data:
                return jsonify(dict(user_data)), 200
            return jsonify({"error": "User not found"}), 404

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/update_user_profile', methods=['POST'])
def update_user_profile():
    try:
        data = request.json
        user_email = data.get('user_email')
        
        with driver.session() as session:
            result = session.run("""
                MATCH (u:User {email: $email})
                SET u.name = $name,
                    u.age = $age,
                    u.height = $height,
                    u.weight = $weight,
                    u.goal = $goal
                RETURN u
            """, {
                "email": user_email,
                "name": data.get('name'),
                "age": int(data.get('age')),
                "height": float(data.get('height')),
                "weight": float(data.get('weight')),
                "goal": data.get('goal')
            })
            
            if result.single():
                return jsonify({"message": "Profile updated successfully"}), 200
            return jsonify({"error": "User not found"}), 404

    except Exception as e:
        return jsonify({"error": str(e)}), 500

def preprocess_image(image_path):
    try:
        # Open and convert image to RGB (in case it's RGBA or grayscale)
        img = Image.open(image_path).convert('RGB')
        
        # Resize the image to match model's expected input size
        img = img.resize((299, 299))
        
        # Convert to numpy array and scale pixels
        img_array = np.array(img)
        img_array = img_array.astype('float32')
        img_array = img_array / 255.0  # Normalize pixel values to [0,1]
        
        # Add batch dimension
        img_array = np.expand_dims(img_array, axis=0)
        
        print(f"Preprocessed image shape: {img_array.shape}")  # Debug info
        print(f"Input shape: {img_array.shape}")
        print(f"Input value range: {img_array.min()} to {img_array.max()}")
        return img_array
        
    except Exception as e:
        print(f"Error in preprocessing: {str(e)}")
        raise e

@app.route('/analyze_image', methods=['POST'])
def analyze_image():
    if 'image' not in request.files:
        return jsonify({"error": "No image uploaded"}), 400

    file = request.files['image']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400

    if file and allowed_file(file.filename):
        try:
            # Upload to Cloudinary first
            upload_result = cloudinary.uploader.upload(file)
            
            # Download the image temporarily for analysis
            response = requests.get(upload_result['secure_url'])
            temp_path = f"/tmp/{secure_filename(file.filename)}"
            
            with open(temp_path, 'wb') as f:
                f.write(response.content)

            # Analyze the image
            image_array = preprocess_image(temp_path)
            predictions = model.predict(image_array)
            
            # Clean up temporary file
            os.remove(temp_path)
            
            # Process results as before
            top_indices = np.argsort(predictions[0])[-3:][::-1]
            results = []
            
            for idx in top_indices:
                results.append({
                    'product': class_names[idx],
                    'probability': float(predictions[0][idx])
                })
            
            return jsonify({
                "message": "Top predictions:",
                "predictions": results
            }), 200

        except Exception as e:
            print(f"Error during image analysis: {str(e)}")
            return jsonify({"error": f"Analysis failed: {str(e)}"}), 500

    return jsonify({"error": "File type not allowed"}), 400

def decode_predictions(predictions):
    # Assuming predictions is a list of probabilities
    predicted_index = predictions.argmax()
    return class_names[predicted_index]

@app.route('/rate_recipe/<recipe_id>', methods=['POST'])
def rate_recipe(recipe_id):
    try:
        data = request.json
        user_email = data.get('user_email')
        rating = int(data.get('rating'))

        with driver.session() as session:
            # Ensure the user and recipe exist
            result = session.run("""
                MATCH (u:User {email: $email})
                MATCH (r:Recipe {recipe_id: $recipe_id})
                MERGE (u)-[ra:RATED]->(r)
                SET ra.rating = $rating
                RETURN r.name as recipe_name
            """, {"email": user_email, "recipe_id": recipe_id, "rating": rating})
            
            record = result.single()
            if record:
                return jsonify({"message": f"Recipe '{record['recipe_name']}' rated successfully"}), 200
            return jsonify({"error": "Recipe or user not found"}), 404

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/get_user_recipes/authored')
def get_authored_recipes():
    try:
        user_email = request.args.get('user_email')
        if not user_email:
            return jsonify({"error": "User email is required"}), 400

        with driver.session() as session:
            # Debug print
            print(f"Fetching authored recipes for user: {user_email}")
            
            result = session.run("""
                MATCH (u:User {email: $email})-[:AUTHORED]->(r:Recipe)
                OPTIONAL MATCH (r)-[:CONTAINS]->(i:Ingredient)
                WITH r, collect(DISTINCT i.name) as ingredients
                RETURN 
                    r.recipe_id as recipe_id,
                    r.name as name,
                    r.instructions as instructions,
                    r.image_path as image_path,
                    r.cuisine as cuisine,
                    r.difficulty as difficulty,
                    r.time as time,
                    r.calories as calories,
                    ingredients
            """, {"email": user_email})
            
            recipes = [dict(record) for record in result]
            print(f"Found {len(recipes)} authored recipes")  # Debug print
            return jsonify(recipes), 200

    except Exception as e:
        print(f"Error getting authored recipes: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/update_user_preferences', methods=['POST'])
def update_user_preferences():
    try:
        data = request.json
        user_email = data.get('user_email')
        
        # Process allergies
        allergies = data.get('allergies', [])
        if data.get('other_allergies'):
            allergies.extend([a.strip() for a in data['other_allergies'].split(',')])
            
        # Process cuisines
        cuisines = data.get('cuisines', [])
        if data.get('other_cuisines'):
            cuisines.extend([c.strip() for c in data['other_cuisines'].split(',')])
            
        # Process food types
        food_types = data.get('food_types', [])
        if data.get('other_food_types'):
            food_types.extend([f.strip() for f in data['other_food_types'].split(',')])
            
        # Process drinks
        drinks = data.get('drinks', [])
        if data.get('other_drinks'):
            drinks.extend([d.strip() for d in data['other_drinks'].split(',')])
            
        with driver.session() as session:
            result = session.run("""
                MATCH (u:User {email: $email})
                SET u.has_allergies = $has_allergies,
                    u.allergies = $allergies,
                    u.diet = $diet,
                    u.other_diet = $other_diet,
                    u.meal_time = $meal_time,
                    u.cuisines = $cuisines,
                    u.food_types = $food_types,
                    u.spice_preference = $spice_preference,
                    u.sweetness_preference = $sweetness_preference,
                    u.disliked_foods = $disliked_foods,
                    u.prep_time = $prep_time,
                    u.drinks = $drinks,
                    u.dietary_goal = $dietary_goal,
                    u.other_goal = $other_goal,
                    u.calorie_preference = $calorie_preference
                RETURN u
            """, {
                "email": user_email,
                "has_allergies": data.get('has_allergies'),
                "allergies": allergies,
                "diet": data.get('diet'),
                "other_diet": data.get('other_diet'),
                "meal_time": data.get('meal_time'),
                "cuisines": cuisines,
                "food_types": food_types,
                "spice_preference": data.get('spice_preference'),
                "sweetness_preference": data.get('sweetness_preference'),
                "disliked_foods": [f.strip() for f in data.get('disliked_foods', '').split(',') if f.strip()],
                "prep_time": data.get('prep_time'),
                "drinks": drinks,
                "dietary_goal": data.get('dietary_goal'),
                "other_goal": data.get('other_goal'),
                "calorie_preference": data.get('calorie_preference')
            })
            
            if result.single():
                return jsonify({"message": "Preferences updated successfully"}), 200
            return jsonify({"error": "User not found"}), 404

    except Exception as e:
        print(f"Error updating user preferences: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/get_user_recipes/added')
def get_added_recipes():
    try:
        user_email = request.args.get('user_email')
        if not user_email:
            return jsonify({"error": "User email is required"}), 400

        with driver.session() as session:
            # Debug print
            print(f"Fetching added recipes for user: {user_email}")
            
            result = session.run("""
                MATCH (u:User {email: $email})-[:ADDED_RECIPE]->(r:Recipe)
                OPTIONAL MATCH (r)-[:CONTAINS]->(i:Ingredient)
                WITH r, collect(DISTINCT i.name) as ingredients
                RETURN 
                    r.recipe_id as recipe_id,
                    r.name as name,
                    r.instructions as instructions,
                    r.image_path as image_path,
                    r.cuisine as cuisine,
                    r.difficulty as difficulty,
                    r.time as time,
                    r.calories as calories,
                    ingredients
            """, {"email": user_email})
            
            recipes = [dict(record) for record in result]
            print(f"Found {len(recipes)} added recipes")  # Debug print
            return jsonify(recipes), 200

    except Exception as e:
        print(f"Error getting added recipes: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/add_fridge_ingredient', methods=['POST'])
def add_fridge_ingredient():
    try:
        data = request.json
        user_email = data.get('user_email')
        category = data.get('category')
        name = data.get('name')
        amount = data.get('amount')
        unit = data.get('unit')
        expiry_date = data.get('expiry_date')

        print("Received data:", data)  # Debug log

        if not all([user_email, category, name, amount, unit, expiry_date]):
            return jsonify({"error": "Missing required fields"}), 400

        with driver.session() as session:
            # Create new ingredient with explicit property types
            ingredient_id = str(uuid.uuid4())
            result = session.run("""
                MATCH (u:User {email: $email})
                CREATE (f:FridgeItem {
                    id: $id,
                    ingredient: $name,
                    category: $category,
                    amount: toFloat($amount),
                    unit: $unit,
                    expiry_date: $expiry_date
                })
                CREATE (u)-[:HAS_IN_FRIDGE]->(f)
                RETURN 
                    f.id as id,
                    f.ingredient as ingredient,
                    f.category as category,
                    f.amount as amount,
                    f.unit as unit,
                    f.expiry_date as expiry_date
            """, {
                "email": user_email,
                "id": ingredient_id,
                "name": name,
                "category": category,
                "amount": amount,
                "unit": unit,
                "expiry_date": expiry_date
            })

            created = result.single()
            if created:
                print("Created item:", dict(created))  # Debug log
                return jsonify(dict(created)), 200
            return jsonify({"error": "Failed to add ingredient"}), 500

    except Exception as e:
        print(f"Error adding ingredient to fridge: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/get_fridge_items')
def get_fridge_items():
    try:
        user_email = request.args.get('user_email')
        if not user_email:
            return jsonify({"error": "User email is required"}), 400

        with driver.session() as session:
            # Modified query to ensure all fields are properly returned
            result = session.run("""
                MATCH (u:User {email: $email})-[:HAS_IN_FRIDGE]->(f:FridgeItem)
                RETURN 
                    f.id as id,
                    f.ingredient as ingredient,
                    f.category as category,
                    f.amount as amount,
                    f.unit as unit,
                    f.expiry_date as expiry_date
                ORDER BY f.expiry_date
            """, {"email": user_email})
            
            # Process each record to ensure proper data types and no null values
            items = []
            for record in result:
                item = {
                    'id': str(record['id']),
                    'ingredient': str(record['ingredient']),
                    'category': str(record['category']),
                    'amount': float(record['amount']) if record['amount'] is not None else 0.0,
                    'unit': str(record['unit']),
                    'expiry_date': str(record['expiry_date'])
                }
                items.append(item)
            
            print("Retrieved items:", items)  # Debug log
            return jsonify(items), 200

    except Exception as e:
        print(f"Error getting fridge items: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/add_fridge_item', methods=['POST'])
def add_fridge_item():
    try:
        data = request.json
        user_email = request.args.get('user_email')
        
        with driver.session() as session:
            result = session.run("""
                MATCH (u:User {email: $email})
                CREATE (i:FridgeItem {
                    id: randomUUID(),
                    name: $name,
                    category: $category,
                    quantity: $quantity,
                    unit: $unit,
                    expiry_date: $expiry_date
                })
                CREATE (u)-[:HAS_ITEM]->(i)
                RETURN i
            """, {
                "email": user_email,
                "name": data['name'],
                "category": data['category'],
                "quantity": float(data['quantity']),
                "unit": data['unit'],
                "expiry_date": data['expiry_date']
            })
            
            if result.single():
                return jsonify({"message": "Item added successfully"}), 200
            return jsonify({"error": "Failed to add item"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/remove_fridge_item/<item_id>', methods=['DELETE'])
def remove_fridge_item(item_id):
    try:
        with driver.session() as session:
            result = session.run("""
                MATCH (i:FridgeItem {id: $id})
                DETACH DELETE i
                RETURN count(i) as deleted
            """, {"id": item_id})
            
            if result.single()['deleted'] > 0:
                return jsonify({"message": "Item removed successfully"}), 200
            return jsonify({"error": "Item not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Add this new route after your other routes
@app.route('/search_recipes_by_ingredient')
def search_recipes_by_ingredient():
    try:
        ingredient = request.args.get('ingredient', '').lower()
        
        with driver.session() as session:
            query = """
            MATCH (r:Recipe)-[:CONTAINS]->(i:Ingredient)
            WHERE toLower(i.name) CONTAINS $ingredient
            WITH r, collect(i.name) as ingredients
            RETURN 
                r.recipe_id as recipe_id,
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
                "ingredient": ingredient
            })
            
            recipes = [dict(record) for record in result]
            return jsonify(recipes), 200
            
    except Exception as e:
        print(f"Error searching recipes by ingredient: {str(e)}")
        return jsonify({"error": str(e)}), 500

# Add these routes after your existing routes

@app.route('/add_to_fridge', methods=['POST'])
def add_to_fridge():
    try:
        data = request.json
        user_email = data.get('user_email')
        ingredient = data.get('ingredient')
        expiry_date = data.get('expiry_date')

        print(f"Adding to fridge: {user_email}, {ingredient}, {expiry_date}")  # Debug log

        if not all([user_email, ingredient, expiry_date]):
            return jsonify({"error": "Missing required fields"}), 400

        with driver.session() as session:
            result = session.run("""
                MATCH (u:User {email: $email})
                CREATE (f:FridgeItem {
                    id: toString(timestamp()),
                    ingredient: $ingredient,
                    expiry_date: $expiry_date,
                    added_date: datetime()
                })
                CREATE (u)-[:HAS_IN_FRIDGE]->(f)
                RETURN 
                    f.id as id, 
                    f.ingredient as ingredient, 
                    toString(f.expiry_date) as expiry_date,
                    toString(f.added_date) as added_date
            """, {
                "email": user_email,
                "ingredient": ingredient,
                "expiry_date": expiry_date
            })

            created_item = result.single()
            if created_item:
                return jsonify({
                    "message": "Ingredient added to fridge successfully",
                    "item": dict(created_item)
                }), 200
            return jsonify({"error": "Failed to add ingredient"}), 500

    except Exception as e:
        print(f"Error adding to fridge: {str(e)}")  # Debug log
        return jsonify({"error": str(e)}), 500

@app.route('/get_user_fridge')
def get_user_fridge():
    try:
        user_email = request.args.get('user_email')
        if not user_email:
            return jsonify({"error": "User email is required"}), 400

        print(f"Getting fridge items for: {user_email}")  # Debug log

        with driver.session() as session:
            result = session.run("""
                MATCH (u:User {email: $email})-[:HAS_IN_FRIDGE]->(f:FridgeItem)
                RETURN 
                    f.id as id,
                    f.ingredient as ingredient,
                    toString(f.expiry_date) as expiry_date,
                    toString(f.added_date) as added_date
                ORDER BY f.expiry_date
            """, {"email": user_email})
            
            items = [dict(record) for record in result]
            print(f"Found {len(items)} items in fridge")  # Debug log
            return jsonify(items), 200

    except Exception as e:
        print(f"Error getting fridge items: {str(e)}")  # Debug log
        return jsonify({"error": str(e)}), 500

@app.route('/remove_from_fridge/<item_id>', methods=['DELETE'])
def remove_from_fridge(item_id):
    try:
        user_email = request.json.get('user_email')
        if not user_email:
            return jsonify({"error": "User email is required"}), 400

        with driver.session() as session:
            # Verify the item belongs to the user before deleting
            result = session.run("""
                MATCH (u:User {email: $email})-[:HAS_IN_FRIDGE]->(f:FridgeItem {id: $item_id})
                DETACH DELETE f
                RETURN count(f) as deleted
            """, {
                "email": user_email,
                "item_id": item_id
            })
            
            if result.single()['deleted'] > 0:
                return jsonify({"message": "Item removed successfully"}), 200
            return jsonify({"error": "Item not found or unauthorized"}), 404

    except Exception as e:
        print(f"Error removing from fridge: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/add_to_shopping_list', methods=['POST'])
def add_to_shopping_list():
    try:
        data = request.json
        user_email = data.get('user_email')
        item = data.get('item')

        if not all([user_email, item]):
            return jsonify({"error": "Missing required fields"}), 400

        with driver.session() as session:
            result = session.run("""
                MATCH (u:User {email: $email})
                CREATE (s:ShoppingItem {
                    id: randomUUID(),
                    name: $item,
                    added_date: datetime(),
                    checked: false
                })
                CREATE (u)-[:HAS_IN_SHOPPING_LIST]->(s)
                RETURN s
            """, {
                "email": user_email,
                "item": item
            })

            if result.single():
                return jsonify({"message": "Item added to shopping list"}), 200
            return jsonify({"error": "Failed to add item"}), 500

    except Exception as e:
        print(f"Error adding to shopping list: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/get_shopping_list')
def get_shopping_list():
    try:
        user_email = request.args.get('user_email')
        if not user_email:
            return jsonify({"error": "User email is required"}), 400

        with driver.session() as session:
            result = session.run("""
                MATCH (u:User {email: $email})-[:HAS_IN_SHOPPING_LIST]->(s:ShoppingItem)
                RETURN s.id as id,
                       s.name as name,
                       s.checked as checked,
                       s.added_date as added_date
                ORDER BY s.added_date DESC
            """, {"email": user_email})
            
            items = [dict(record) for record in result]
            return jsonify(items), 200

    except Exception as e:
        print(f"Error getting shopping list: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/update_shopping_item/<item_id>', methods=['PUT'])
def update_shopping_item(item_id):
    try:
        data = request.json
        user_email = data.get('user_email')
        checked = data.get('checked', False)

        with driver.session() as session:
            result = session.run("""
                MATCH (u:User {email: $email})-[:HAS_IN_SHOPPING_LIST]->(s:ShoppingItem {id: $item_id})
                SET s.checked = $checked
                RETURN s
            """, {
                "email": user_email,
                "item_id": item_id,
                "checked": checked
            })

            if result.single():
                return jsonify({"message": "Item updated successfully"}), 200
            return jsonify({"error": "Item not found or unauthorized"}), 404

    except Exception as e:
        print(f"Error updating shopping item: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/remove_from_shopping_list/<item_id>', methods=['DELETE'])
def remove_from_shopping_list(item_id):
    try:
        user_email = request.json.get('user_email')
        if not user_email:
            return jsonify({"error": "User email is required"}), 400

        with driver.session() as session:
            result = session.run("""
                MATCH (u:User {email: $email})-[:HAS_IN_SHOPPING_LIST]->(s:ShoppingItem {id: $item_id})
                DETACH DELETE s
                RETURN count(s) as deleted
            """, {
                "email": user_email,
                "item_id": item_id
            })
            
            if result.single()['deleted'] > 0:
                return jsonify({"message": "Item removed successfully"}), 200
            return jsonify({"error": "Item not found or unauthorized"}), 404

    except Exception as e:
        print(f"Error removing from shopping list: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/get_recipes_from_fridge')
def get_recipes_from_fridge():
    try:
        user_email = request.args.get('user_email')
        if not user_email:
            return jsonify({"error": "User email is required"}), 400

        with driver.session() as session:
            # Updated query to exclude expired ingredients
            result = session.run("""
                // First get all non-expired ingredients from user's fridge
                MATCH (u:User {email: $email})-[:HAS_IN_FRIDGE]->(f:FridgeItem)
                WHERE datetime(f.expiry_date) > datetime()  // Only include non-expired items
                WITH collect(toLower(f.ingredient)) as fridge_ingredients
                
                // Then find recipes that contain these ingredients
                MATCH (r:Recipe)-[:CONTAINS]->(i:Ingredient)
                WITH r, fridge_ingredients, 
                     collect(toLower(i.name)) as recipe_ingredients,
                     size(collect(i.name)) as total_ingredients
                
                // Calculate how many ingredients from the recipe are in the fridge
                WITH r, 
                     size([x IN recipe_ingredients WHERE x IN fridge_ingredients]) as matching_ingredients,
                     total_ingredients,
                     recipe_ingredients
                
                // Calculate match percentage and only return recipes with at least one matching ingredient
                WHERE matching_ingredients > 0
                
                // Get all ingredients for these recipes
                MATCH (r)-[:CONTAINS]->(all_i:Ingredient)
                WITH r, 
                     matching_ingredients,
                     total_ingredients,
                     collect(DISTINCT all_i.name) as all_ingredients,
                     (toFloat(matching_ingredients) / total_ingredients * 100) as match_percentage
                
                // Return recipe details with match information
                RETURN 
                    r.recipe_id as recipe_id,
                    r.name as name,
                    r.instructions as instructions,
                    r.image_path as image_path,
                    r.cuisine as cuisine,
                    r.difficulty as difficulty,
                    r.time as time,
                    r.calories as calories,
                    all_ingredients as ingredients,
                    matching_ingredients,
                    total_ingredients,
                    match_percentage
                ORDER BY match_percentage DESC
                LIMIT 10
            """, {"email": user_email})
            
            recipes = [dict(record) for record in result]
            return jsonify(recipes), 200

    except Exception as e:
        print(f"Error getting recipe recommendations: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/get_recipe/<recipe_id>')
def get_recipe(recipe_id):
    try:
        with driver.session() as session:
            result = session.run("""
                MATCH (r:Recipe {recipe_id: $recipe_id})
                OPTIONAL MATCH (r)-[:CONTAINS]->(i:Ingredient)
                WITH r, collect(DISTINCT i.name) as ingredients
                RETURN 
                    r.recipe_id as recipe_id,
                    r.name as name,
                    r.instructions as instructions,
                    r.image_path as image_path,
                    r.cuisine as cuisine,
                    r.difficulty as difficulty,
                    r.time as time,
                    r.calories as calories,
                    ingredients
            """, {"recipe_id": recipe_id})
            
            record = result.single()
            if record:
                return jsonify(dict(record)), 200
            return jsonify({"error": "Recipe not found"}), 404

    except Exception as e:
        print(f"Error getting recipe details: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/get_recipe_recommendations')
def get_recipe_recommendations():
    try:
        user_email = request.args.get('user_email')
        if not user_email:
            return jsonify({"error": "User email is required"}), 400

        with driver.session() as session:
            # Get user preferences
            user_prefs = session.run("""
                MATCH (u:User {email: $email})
                RETURN u
            """, {"email": user_email}).single()

            if not user_prefs:
                return jsonify({"error": "User not found"}), 404

            # Build query based on user preferences
            query = """
                MATCH (r:Recipe)-[:CONTAINS]->(i:Ingredient)
                WITH r, collect(DISTINCT i.name) as ingredients
                WHERE 
                    // Filter by diet if specified
                    (NOT exists(r.diet) OR r.diet = $diet)
                    // Filter by calorie preference
                    AND (NOT exists(r.calories) OR 
                        CASE $calorie_preference
                            WHEN 'low' THEN r.calories <= 200
                            WHEN 'medium' THEN r.calories > 200 AND r.calories <= 500
                            WHEN 'high' THEN r.calories > 500
                            ELSE true
                        END)
                    // Filter out recipes with disliked ingredients
                    AND NONE(x IN $disliked_foods WHERE toLower(r.name) CONTAINS toLower(x))
                    AND NONE(x IN $disliked_foods WHERE any(ing IN ingredients WHERE toLower(ing) CONTAINS toLower(x)))
                RETURN 
                    r.recipe_id as recipe_id,
                    r.name as name,
                    r.instructions as instructions,
                    r.image_path as image_path,
                    r.cuisine as cuisine,
                    r.difficulty as difficulty,
                    r.time as time,
                    r.calories as calories,
                    ingredients,
                    // Calculate match percentage based on preferences
                    CASE
                        WHEN r.cuisine IN $preferred_cuisines THEN 20
                        ELSE 0
                    END +
                    CASE
                        WHEN r.difficulty = $skill_level THEN 15
                        ELSE 0
                    END +
                    CASE
                        WHEN r.time <= toInteger($prep_time) THEN 15
                        ELSE 0
                    END as match_percentage
                ORDER BY match_percentage DESC
                LIMIT 10
            """

            # Get user preferences from the database
            user = user_prefs['u']
            
            # Process disliked foods
            disliked_foods = []
            if user.get('disliked_foods'):
                disliked_foods = [food.strip().lower() for food in user['disliked_foods']]

            # Execute recommendation query
            result = session.run(query, {
                "email": user_email,
                "diet": user.get('diet'),
                "calorie_preference": user.get('calorie_preference'),
                "preferred_cuisines": user.get('cuisines', []),
                "skill_level": user.get('cooking_skill'),
                "prep_time": user.get('preferred_cooking_time', 60),
                "disliked_foods": disliked_foods
            })

            recipes = [dict(record) for record in result]
            return jsonify(recipes), 200

    except Exception as e:
        print(f"Error getting recipe recommendations: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/add_to_recipe_list', methods=['POST'])
def add_to_recipe_list():
    try:
        data = request.json
        user_email = data.get('user_email')
        recipe_id = data.get('recipe_id')
        list_type = data.get('list_type')

        if not all([user_email, recipe_id, list_type]):
            return jsonify({"error": "Missing required parameters"}), 400

        # Map list_type to relationship type
        relationship_types = {
            'liked': 'LIKES',
            'cooked': 'COOKED',
            'want_to_try': 'WANTS_TO_TRY'
        }

        relationship_type = relationship_types.get(list_type)
        if not relationship_type:
            return jsonify({"error": "Invalid list type"}), 400

        with driver.session() as session:
            # Create relationship between user and recipe
            result = session.run("""
                MATCH (u:User {email: $email})
                MATCH (r:Recipe {recipe_id: $recipe_id})
                MERGE (u)-[rel:${relationship_type}]->(r)
                RETURN rel
            """, {
                "email": user_email,
                "recipe_id": recipe_id
            })

            if result.single():
                return jsonify({"message": f"Recipe added to {list_type} list successfully"}), 200
            return jsonify({"error": "Failed to add recipe to list"}), 500

    except Exception as e:
        print(f"Error adding recipe to list: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/save_survey', methods=['POST'])
def save_survey():
    try:
        data = request.json
        user_email = data.get('user_email')
        survey_data = data.get('survey_data')

        print("Received survey data:", data)  # Debug log

        if not user_email or not survey_data:
            return jsonify({"error": "Missing required fields"}), 400

        with driver.session() as session:
            # First, remove any existing survey data
            session.run("""
                MATCH (u:User {email: $email})-[r:HAS_SURVEY]->(s:Survey)
                DELETE r, s
            """, {"email": user_email})

            # Create new survey node with all fields
            result = session.run("""
                MATCH (u:User {email: $email})
                CREATE (s:Survey {
                    dietaryRestrictions: $dietaryRestrictions,
                    cuisinePreferences: $cuisinePreferences,
                    cookingSkill: $cookingSkill,
                    cookingFrequency: $cookingFrequency,
                    mealPreferences: $mealPreferences
                })
                CREATE (u)-[:HAS_SURVEY]->(s)
                RETURN s
            """, {
                "email": user_email,
                "dietaryRestrictions": survey_data['dietaryRestrictions'],
                "cuisinePreferences": survey_data['cuisinePreferences'],
                "cookingSkill": survey_data['cookingSkill'],
                "cookingFrequency": survey_data['cookingFrequency'],
                "mealPreferences": survey_data['mealPreferences']
            })

            record = result.single()
            if record:
                return jsonify({"message": "Survey data saved successfully", "data": dict(record['s'])}), 200
            return jsonify({"error": "Failed to save survey data"}), 500

    except Exception as e:
        print(f"Error saving survey data: {str(e)}")  # Debug log
        return jsonify({"error": str(e)}), 500

@app.route('/get_survey', methods=['GET'])
def get_survey():
    try:
        user_email = request.args.get('user_email')
        if not user_email:
            return jsonify({"error": "User email is required"}), 400

        with driver.session() as session:
            result = session.run("""
                MATCH (u:User {email: $email})-[:HAS_SURVEY]->(s:Survey)
                RETURN s
            """, {"email": user_email})
            
            record = result.single()
            if record:
                return jsonify(dict(record['s'])), 200
            return jsonify({"message": "No survey data found"}), 404

    except Exception as e:
        print(f"Error getting survey data: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/get_recommended_recipes', methods=['GET'])
def get_recommended_recipes():
    try:
        user_email = request.args.get('user_email')
        if not user_email:
            return jsonify({"error": "User email is required"}), 400

        with driver.session() as session:
            # First get user preferences
            result = session.run("""
                MATCH (u:User {email: $email})-[:HAS_SURVEY]->(s:Survey)
                RETURN s
            """, {"email": user_email})
            
            preferences = result.single()
            if not preferences:
                return jsonify({"error": "No preferences found"}), 404

            # Get recipes matching user preferences
            recipes = session.run("""
                MATCH (r:Recipe)
                WHERE 
                    ANY(cuisine IN $cuisines WHERE cuisine IN r.cuisineType)
                    AND NOT ANY(restriction IN $restrictions WHERE restriction IN r.allergens)
                RETURN r
                LIMIT 10
            """, {
                "cuisines": preferences['s']['cuisinePreferences'],
                "restrictions": preferences['s']['dietaryRestrictions']
            })

            recommended_recipes = [dict(record['r']) for record in recipes]
            return jsonify({"recipes": recommended_recipes}), 200

    except Exception as e:
        print(f"Error getting recommended recipes: {str(e)}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True)

