// Get all ingredients for a recipe
MATCH (r:Recipe {recipe_id: 1})-[:CONTAINS]->(i:Ingredient)
RETURN i.name, i.calories_per_unit

// Get all recipes in a specific category
MATCH (c:Category {name: 'Dinner'})<-[:BELONGS_TO]-(r:Recipe)
RETURN r.name, r.time, r.difficulty

// Get recipes containing specific ingredients
MATCH (i:Ingredient)
WHERE i.name IN ['Chicken', 'Pasta']
MATCH (r:Recipe)-[:CONTAINS]->(i)
RETURN r.name, COLLECT(i.name) AS ingredients

// Get average rating for a recipe
MATCH (r:Recipe {recipe_id: 1})<-[:FOR_RECIPE]-(rating:Rating)
RETURN r.name, AVG(rating.score) AS average_rating
