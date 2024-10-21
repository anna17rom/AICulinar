// Create constraints for unique identifiers
CREATE CONSTRAINT user_id IF NOT EXISTS FOR (u:User) REQUIRE u.user_id IS UNIQUE;
CREATE CONSTRAINT recipe_id IF NOT EXISTS FOR (r:Recipe) REQUIRE r.recipe_id IS UNIQUE;
CREATE CONSTRAINT ingredient_id IF NOT EXISTS FOR (i:Ingredient) REQUIRE i.ingredient_id IS UNIQUE;
CREATE CONSTRAINT category_id IF NOT EXISTS FOR (c:Category) REQUIRE c.category_id IS UNIQUE;
CREATE CONSTRAINT goal_id IF NOT EXISTS FOR (g:Goal) REQUIRE g.goal_id IS UNIQUE;
CREATE CONSTRAINT rating_id IF NOT EXISTS FOR (r:Rating) REQUIRE r.rating_id IS UNIQUE;
CREATE CONSTRAINT ingredient_category_id IF NOT EXISTS FOR (ic:Ingredient_Category) REQUIRE ic.category_id IS UNIQUE;

// Create indexes for faster querying
CREATE INDEX user_name_index IF NOT EXISTS FOR (u:User) ON (u.name);
CREATE INDEX recipe_name_index IF NOT EXISTS FOR (r:Recipe) ON (r.name);
CREATE INDEX ingredient_name_index IF NOT EXISTS FOR (i:Ingredient) ON (i.name);
