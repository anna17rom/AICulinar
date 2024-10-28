#!/bin/bash

# Stop any running containers
docker-compose down -v

# Start the containers
docker-compose up --build -d

# Wait for services to be ready
echo "Waiting for services to start..."
sleep 15

# Initialize test data
curl http://localhost:5000/init_test_data

echo "Services are ready!"
echo "Web application: http://localhost:5000"
echo "Neo4j Browser: http://localhost:7474"
