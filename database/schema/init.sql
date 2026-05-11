-- Database Initialization Script
-- This script creates the necessary extensions and deploys the full schema

-- Enable required PostgreSQL extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Log the initialization
DO $$
BEGIN
    RAISE NOTICE 'AI GarminCoach Database Initialization Starting';
    RAISE NOTICE 'Extensions enabled: uuid-ossp, pgcrypto';
    RAISE NOTICE 'Ready for schema deployment';
END $$; 