// Create Users
CREATE (u1:User {user_id: 1, name: 'John Doe', age: 30, weight: 80, height: 180, preferences: ['spicy food'], goals: ['weight loss']});
CREATE (u2:User {user_id: 2, name: 'Jane Smith', age: 25, weight: 65, height: 165, preferences: ['vegetarian'], goals: ['muscle gain']});

// Create Recipes
CREATE (r1:Recipe {recipe_id: 1, name: 'Spicy Chicken Curry', time: 45, difficulty: 'Medium', calories: 450, category: 'Dinner', cuisine: 'Indian'});
CREATE (r2:Recipe {recipe_id: 2, name: 'Vegetarian Pasta', time: 30, difficulty: 'Easy', calories: 350, category: 'Lunch', cuisine: 'Italian'});

// Create Ingredients
CREATE (i1:Ingredient {ingredient_id: 1, name: 'Chicken', calories_per_unit: 165, category: 'Meat'});
CREATE (i2:Ingredient {ingredient_id: 2, name: 'Pasta', calories_per_unit: 131, category: 'Grains'});
CREATE (i3:Ingredient {ingredient_id: 3, name: 'Tomato', calories_per_unit: 18, category: 'Vegetables'});

// Create Categories
CREATE (c1:Category {category_id: 1, name: 'Dinner'});
CREATE (c2:Category {category_id: 2, name: 'Lunch'});

// Create Goals
CREATE (g1:Goal {goal_id: 1, description: 'Weight loss'});
CREATE (g2:Goal {goal_id: 2, description: 'Muscle gain'});

// Create Ingredient Categories
CREATE (ic1:Ingredient_Category {category_id: 1, name: 'Meat'});
CREATE (ic2:Ingredient_Category {category_id: 2, name: 'Grains'});
CREATE (ic3:Ingredient_Category {category_id: 3, name: 'Vegetables'});

// Create relationships
MATCH (u:User {user_id: 1}), (r:Recipe {recipe_id: 1})
CREATE (u)-[:ADDED_RECIPE]->(r);

MATCH (u:User {user_id: 2}), (r:Recipe {recipe_id: 2})
CREATE (u)-[:ADDED_RECIPE]->(r);

MATCH (r:Recipe {recipe_id: 1}), (i:Ingredient {ingredient_id: 1})
CREATE (r)-[:CONTAINS]->(i);

MATCH (r:Recipe {recipe_id: 2}), (i:Ingredient {ingredient_id: 2})
CREATE (r)-[:CONTAINS]->(i);

MATCH (r:Recipe {recipe_id: 2}), (i:Ingredient {ingredient_id: 3})
CREATE (r)-[:CONTAINS]->(i);

MATCH (r:Recipe {recipe_id: 1}), (c:Category {category_id: 1})
CREATE (r)-[:BELONGS_TO]->(c);

MATCH (r:Recipe {recipe_id: 2}), (c:Category {category_id: 2})
CREATE (r)-[:BELONGS_TO]->(c);

MATCH (u:User {user_id: 1}), (g:Goal {goal_id: 1})
CREATE (u)-[:HAS_GOAL]->(g);

MATCH (u:User {user_id: 2}), (g:Goal {goal_id: 2})
CREATE (u)-[:HAS_GOAL]->(g);

MATCH (i:Ingredient {ingredient_id: 1}), (ic:Ingredient_Category {category_id: 1})
CREATE (i)-[:PART_OF]->(ic);

MATCH (i:Ingredient {ingredient_id: 2}), (ic:Ingredient_Category {category_id: 2})
CREATE (i)-[:PART_OF]->(ic);

MATCH (i:Ingredient {ingredient_id: 3}), (ic:Ingredient_Category {category_id: 3})
CREATE (i)-[:PART_OF]->(ic);
