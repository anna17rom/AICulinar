#!/bin/bash
until cypher-shell -u neo4j -p your_password "MATCH (n) RETURN n LIMIT 1"; do
  echo "Waiting for Neo4j to be ready..."
  sleep 1
done

echo "Initializing database..."
cypher-shell -u neo4j -p saksuguan< setup/database_setup.cypher
cypher-shell -u neo4j -p saksuguan < setup/sample_data.cypher
