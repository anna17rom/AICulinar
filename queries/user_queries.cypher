// Get all recipes added by a user
MATCH (u:User {user_id: 1})-[:ADDED_RECIPE]->(r:Recipe)
RETURN r.name, r.time, r.difficulty, r.calories

// Get user's goals
MATCH (u:User {user_id: 1})-[:HAS_GOAL]->(g:Goal)
RETURN g.description

// Get recipes recommended to a user
MATCH (u:User {user_id: 1})<-[:RECOMMENDED_TO]-(r:Recipe)
RETURN r.name, r.cuisine, r.calories

// Track user's weight (create a new Weight_Entry node)
MATCH (u:User {user_id: 1})
CREATE (w:Weight_Entry {date: date(), weight: 79.5})
CREATE (u)-[:TRACKS_WEIGHT]->(w)

// Get user's weight history
MATCH (u:User {user_id: 1})-[:TRACKS_WEIGHT]->(w:Weight_Entry)
RETURN w.date, w.weight
ORDER BY w.date DESC
