from flask import Flask, request, jsonify
import sqlite3

app = Flask(__name__)

# Initialize database
def init_db():
    conn = sqlite3.connect('recipes.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS recipes
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  name TEXT NOT NULL,
                  ingredients TEXT NOT NULL,
                  instructions TEXT NOT NULL)''')
    conn.commit()
    conn.close()

init_db()

@app.route('/')
def index():
    return app.send_static_file('index.html')

@app.route('/add_recipe', methods=['POST'])
def add_recipe():
    data = request.json
    conn = sqlite3.connect('recipes.db')
    c = conn.cursor()
    c.execute("INSERT INTO recipes (name, ingredients, instructions) VALUES (?, ?, ?)",
              (data['name'], data['ingredients'], data['instructions']))
    conn.commit()
    conn.close()
    return jsonify({"message": "Recipe added successfully"}), 201

@app.route('/get_recipes', methods=['GET'])
def get_recipes():
    conn = sqlite3.connect('recipes.db')
    c = conn.cursor()
    c.execute("SELECT * FROM recipes")
    recipes = [{"id": row[0], "name": row[1], "ingredients": row[2], "instructions": row[3]} for row in c.fetchall()]
    conn.close()
    return jsonify(recipes)

if __name__ == '__main__':
    app.run(debug=True)
