#!/bin/bash

# AI GarminCoach Development Environment Setup Script
# This script sets up the complete development environment (No Docker Desktop required)

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}===========================================${NC}"
echo -e "${BLUE}AI GarminCoach Development Setup${NC}"
echo -e "${BLUE}===========================================${NC}"

# Function to print colored messages
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if Python 3.12+ is available
check_python() {
    print_status "Checking Python version..."
    
    if command -v python3.12 &> /dev/null; then
        PYTHON_CMD="python3.12"
    elif command -v python3 &> /dev/null; then
        PYTHON_VERSION=$(python3 --version | cut -d' ' -f2 | cut -d'.' -f1,2)
        if (( $(echo "$PYTHON_VERSION >= 3.12" | bc -l) )); then
            PYTHON_CMD="python3"
        else
            print_error "Python 3.12+ is required. Found: $PYTHON_VERSION"
            exit 1
        fi
    else
        print_error "Python 3.12+ is required but not found"
        exit 1
    fi
    
    print_status "Using Python: $PYTHON_CMD ($($PYTHON_CMD --version))"
}

# Check database preferences
check_database_preference() {
    print_status "Checking database options..."
    
    # Check if PostgreSQL is available
    if command -v psql &> /dev/null; then
        print_status "PostgreSQL found: $(psql --version)"
        DB_TYPE="postgresql"
    elif command -v brew &> /dev/null; then
        print_status "Homebrew found - PostgreSQL can be installed"
        DB_TYPE="postgresql_install"
    else
        print_status "PostgreSQL not found, will use SQLite"
        DB_TYPE="sqlite"
    fi
    
    echo -e "${YELLOW}Database Options:${NC}"
    echo -e "1. PostgreSQL (recommended for full features)"
    echo -e "2. SQLite (simple, file-based)"
    echo -e ""
    read -p "Choose database type (1 for PostgreSQL, 2 for SQLite): " choice
    
    case $choice in
        1)
            DB_TYPE="postgresql"
            ;;
        2)
            DB_TYPE="sqlite"
            ;;
        *)
            print_status "Invalid choice, defaulting to SQLite"
            DB_TYPE="sqlite"
            ;;
    esac
}

# Create virtual environment
setup_venv() {
    print_status "Setting up Python virtual environment..."
    
    # Check if virtual environment exists and is valid
    if [ ! -d "venv" ] || [ ! -f "venv/bin/activate" ]; then
        if [ -d "venv" ]; then
            print_warning "Virtual environment exists but is corrupted. Recreating..."
            rm -rf venv
        fi
        
        print_status "Creating virtual environment..."
        $PYTHON_CMD -m venv venv
        print_status "Virtual environment created"
    else
        print_status "Virtual environment already exists and is valid"
    fi
    
    # Activate virtual environment
    if [ -f "venv/bin/activate" ]; then
        source venv/bin/activate
        print_status "Virtual environment activated"
    else
        print_error "Virtual environment activation failed - activate script not found"
        exit 1
    fi
    
    # Upgrade pip
    pip install --upgrade pip
    
    # Install dependencies
    if [ -f "requirements.txt" ]; then
        print_status "Installing dependencies from requirements.txt..."
        pip install -r requirements.txt
    else
        print_status "Installing dependencies from pyproject.toml..."
        pip install -e .
    fi
    
    print_status "Dependencies installed successfully"
}

# Set up environment variables
setup_env() {
    print_status "Setting up environment variables..."
    
    if [ ! -f ".env" ]; then
        if [ -f ".env.example" ]; then
            cp .env.example .env
            print_status "Created .env file from .env.example"
            print_warning "Please edit .env file with your actual credentials"
        else
            print_error ".env.example file not found"
            exit 1
        fi
    else
        print_status ".env file already exists"
    fi
    
    # Update database configuration based on choice
    if [ "$DB_TYPE" = "sqlite" ]; then
        print_status "Configuring for SQLite database..."
        if ! grep -q "DATABASE_URL=sqlite" .env; then
            sed -i.bak 's|DATABASE_URL=.*|DATABASE_URL=sqlite:///data/ai_garmin_coach.db|' .env
            print_status "Database URL updated for SQLite"
        fi
    else
        print_status "Configuring for PostgreSQL database..."
        if ! grep -q "DATABASE_URL=postgresql" .env; then
            sed -i.bak 's|DATABASE_URL=.*|DATABASE_URL=postgresql://dev_user:dev_password@localhost:5432/ai_garmin_coach|' .env
            print_status "Database URL updated for PostgreSQL"
        fi
    fi
}

# Set up PostgreSQL database
setup_postgresql() {
    print_status "Setting up PostgreSQL database..."
    
    # Check if PostgreSQL is running
    if ! pg_isready -h localhost -p 5432 > /dev/null 2>&1; then
        if command -v brew &> /dev/null; then
            print_status "Installing PostgreSQL via Homebrew..."
            brew install postgresql@14
            brew services start postgresql@14
            
            # Wait for PostgreSQL to start
            print_status "Waiting for PostgreSQL to start..."
            for i in {1..30}; do
                if pg_isready -h localhost -p 5432 > /dev/null 2>&1; then
                    print_status "PostgreSQL is ready"
                    break
                fi
                if [ $i -eq 30 ]; then
                    print_error "PostgreSQL failed to start after 30 seconds"
                    exit 1
                fi
                sleep 1
            done
        else
            print_error "PostgreSQL is not running and Homebrew is not available"
            print_error "Please install PostgreSQL manually or choose SQLite"
            exit 1
        fi
    fi
    
    # Create user and database
    print_status "Creating database and user..."
    
    # Create user if not exists
    if ! psql -h localhost -c "SELECT 1 FROM pg_user WHERE usename = 'dev_user'" | grep -q 1; then
        createuser -s dev_user
        print_status "Created user: dev_user"
    fi
    
    # Create database if not exists
    if ! psql -h localhost -lqt | cut -d \| -f 1 | grep -qw ai_garmin_coach; then
        createdb -O dev_user ai_garmin_coach
        print_status "Created database: ai_garmin_coach"
    fi
    
    # Add extensions
    psql -h localhost -d ai_garmin_coach -c "CREATE EXTENSION IF NOT EXISTS pgcrypto;"
    psql -h localhost -d ai_garmin_coach -c "CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\";"
    
    print_status "PostgreSQL setup complete"
}

# Set up SQLite database
setup_sqlite() {
    print_status "Setting up SQLite database..."
    
    # Create data directory
    mkdir -p data
    
    print_status "SQLite setup complete (database will be created automatically)"
}

# Set up database
setup_database() {
    if [ "$DB_TYPE" = "sqlite" ]; then
        setup_sqlite
    else
        setup_postgresql
    fi
}

# Run database migrations
run_migrations() {
    print_status "Running database migrations..."
    
    if [ "$DB_TYPE" = "postgresql" ]; then
        # Check if tables exist
        TABLE_COUNT=$(psql -h localhost -d ai_garmin_coach -t -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public';" 2>/dev/null | tr -d ' ' || echo "0")
        
        if [ "$TABLE_COUNT" -eq "0" ]; then
            print_status "Creating database tables..."
            if [ -f "database/schema/database_schema.sql" ]; then
                psql -h localhost -d ai_garmin_coach -f database/schema/database_schema.sql
                print_status "Database schema deployed"
            else
                print_warning "Database schema file not found. Tables will be created automatically."
            fi
        else
            print_status "Database tables already exist"
        fi
    else
        print_status "Using SQLite - schema will be created automatically by application"
    fi
}

# Generate encryption keys
generate_keys() {
    print_status "Generating encryption keys..."
    
    # Check if keys exist in .env
    if ! grep -q "SECRET_KEY=" .env || ! grep -q "ENCRYPTION_KEY=" .env; then
        print_status "Generating new encryption keys..."
        
        # Generate secret key
        SECRET_KEY=$(openssl rand -hex 32)
        
        # Generate encryption key (Fernet compatible)
        ENCRYPTION_KEY=$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
        
        # Update .env file
        if ! grep -q "SECRET_KEY=" .env; then
            echo "SECRET_KEY=$SECRET_KEY" >> .env
        fi
        
        if ! grep -q "ENCRYPTION_KEY=" .env; then
            echo "ENCRYPTION_KEY=$ENCRYPTION_KEY" >> .env
        fi
        
        print_status "Encryption keys generated and added to .env"
    else
        print_status "Encryption keys already exist in .env"
    fi
}

# Test the setup
test_setup() {
    print_status "Testing setup..."
    
    # Test database connection
    if [ "$DB_TYPE" = "postgresql" ]; then
        if psql -h localhost -d ai_garmin_coach -c "SELECT 1;" > /dev/null 2>&1; then
            print_status "PostgreSQL connection: OK"
        else
            print_error "PostgreSQL connection: FAILED"
            exit 1
        fi
    else
        print_status "SQLite connection: OK (will be tested at runtime)"
    fi
    
    # Test Python imports
    if [ -f "venv/bin/activate" ]; then
        source venv/bin/activate
    else
        print_error "Virtual environment not found for testing"
        exit 1
    fi
    
    if $PYTHON_CMD -c "import google.genai; import telegram; import garminconnect; print('All imports successful')" > /dev/null 2>&1; then
        print_status "Python dependencies: OK"
    else
        print_error "Python dependencies: FAILED"
        print_error "Please check your virtual environment and dependencies"
        exit 1
    fi
    
    print_status "Setup test completed successfully"
}

# Display next steps
show_next_steps() {
    echo -e "${BLUE}===========================================${NC}"
    echo -e "${GREEN}Setup completed successfully!${NC}"
    echo -e "${BLUE}===========================================${NC}"
    echo
    echo -e "${YELLOW}Next steps:${NC}"
    echo -e "1. Edit ${YELLOW}.env${NC} file with your actual credentials:"
    echo -e "   - ${YELLOW}GOOGLE_API_KEY${NC}: Your Google Gen AI API key"
    echo -e "   - ${YELLOW}TELEGRAM_BOT_TOKEN${NC}: Your Telegram bot token"
    echo -e "   - ${YELLOW}GOOGLE_CLOUD_PROJECT${NC}: Your GCP project ID"
    echo
    echo -e "2. Start the development environment:"
    echo -e "   ${BLUE}source venv/bin/activate${NC}"
    echo -e "   ${BLUE}python src/main.py${NC}"
    echo
    if [ "$DB_TYPE" = "postgresql" ]; then
        echo -e "3. Access PostgreSQL:"
        echo -e "   ${BLUE}psql -h localhost -d ai_garmin_coach -U dev_user${NC}"
        echo
    fi
    echo -e "${GREEN}Happy coding! 🚀${NC}"
}

# Main execution
main() {
    check_python
    check_database_preference
    setup_venv
    setup_env
    setup_database
    run_migrations
    generate_keys
    test_setup
    show_next_steps
}

main "$@" 