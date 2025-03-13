# aiculinar

**aiculinar** is a lightweight, AI-driven cooking application designed to help you explore, create, and manage recipes. It offers quick search, recipe recommendations, Neo4j graph database integration, and containerized deployment for easy setup.

## Features
- **Recipe Search & Management**: Browse, filter, and organize recipes by ingredients or cuisine.
- **AI Suggestions**: Get personalized recommendations based on your preferences.
- **Neo4j Integration**: Store and query recipes in a graph database, enabling more flexible and powerful data relationships.
- **Containerized Deployment**: Quickly spin up the app using Docker.

## How to Run

1. **Clone the Repository**
   ```bash
   git clone https://github.com/yourusername/aiculinar.git
   cd aiculinar
   ```

2. **Set Up Environment**
   - Update any required variables in `.env` or the `docker-compose.yml` file (e.g., API keys, Neo4j credentials).

3. **Build and Run**
   ```bash
   docker-compose up -d
   ```
   This command starts all necessary services (web server, Neo4j, etc.) in Docker containers.

4. **Access the Application**
   - Open `http://localhost:3000` in your browser (or the port specified in `docker-compose.yml`).

Enjoy cooking with **aiculinar**!
