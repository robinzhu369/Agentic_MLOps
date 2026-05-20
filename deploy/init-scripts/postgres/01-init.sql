-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Create schemas for different modules
CREATE SCHEMA IF NOT EXISTS agent;
CREATE SCHEMA IF NOT EXISTS feast;
CREATE SCHEMA IF NOT EXISTS rag;
