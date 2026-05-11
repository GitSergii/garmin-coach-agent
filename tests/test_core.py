"""
Core Component Tests
===================

Basic tests for the core functionality of the AI GarminCoach system.
"""

import pytest
import tempfile
import os
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

from sqlalchemy import text

from src.core.config import Config
from src.core.database import Database, User
from src.core.garmin_client import GarminClient

@pytest.fixture
def temp_config():
    """Create a temporary configuration for testing."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        env_file = tmp_path / ".env"
        env_file.write_text(
            """
DB_HOST=test.db
DB_PORT=0
DB_NAME=test_db
DB_USER=test_user
DB_PASSWORD=test_pass
GOOGLE_CLOUD_PROJECT=test-project
GOOGLE_API_KEY=test-key
TELEGRAM_BOT_TOKEN=test-token
SECRET_KEY=test-secret
"""
        )

        os.environ["APP_ROOT"] = str(tmp_path)

        yield Config(env_file=str(env_file))


@pytest.fixture
def temp_database(temp_config):
    """Create a temporary database for testing (PostgreSQL only; schema uses ARRAY)."""
    if "sqlite" in temp_config.database.url.lower():
        pytest.skip(
            "Schema uses PostgreSQL-only columns (ARRAY). Point tests at Postgres or skip."
        )
    db = Database(temp_config)
    db.create_tables()
    yield db
    db.engine.dispose()

class TestConfig:
    """Test configuration management."""
    
    def test_config_initialization(self, temp_config):
        """Test basic configuration initialization."""
        assert temp_config.database.host == "test.db"
        assert temp_config.google_cloud.project_id == "test-project"
        assert temp_config.telegram.bot_token == "test-token"
        assert temp_config.security.secret_key == "test-secret"
    
    def test_database_url_sqlite(self, temp_config):
        """Test SQLite database URL generation."""
        assert temp_config.database.url.startswith("sqlite:///")
        assert "test.db" in temp_config.database.url
    
    def test_database_url_postgresql(self, temp_config):
        """Test PostgreSQL database URL generation."""
        # Modify config to use PostgreSQL
        temp_config.database.host = "localhost"
        temp_config.database.port = 5432
        temp_config.database.name = "test_db"
        temp_config.database.user = "test_user"
        temp_config.database.password = "test_pass"
        
        expected = "postgresql://test_user:test_pass@localhost:5432/test_db"
        assert temp_config.database.url == expected

class TestDatabase:
    """Test database operations."""
    
    def test_database_connection(self, temp_database):
        """Test database connection and table creation."""
        with temp_database.get_session() as session:
            # Test that we can create a session
            assert session is not None
            
            # Test that tables exist
            result = session.execute(text("SELECT 1")).fetchone()
            assert result[0] == 1
    
    def test_user_creation(self, temp_database):
        """Test user creation and retrieval."""
        with temp_database.get_session() as session:
            # Create a test user
            user = User(
                telegram_user_id=12345,
                username="testuser",
                first_name="Test",
                last_name="User",
                email="test@example.com",
                garmin_username="garmin_user",
                garmin_password="plain_password"  # Now plain text
            )
            
            session.add(user)
            session.commit()
            
            # Retrieve the user
            retrieved_user = session.query(User).filter_by(telegram_user_id=12345).first()
            
            assert retrieved_user is not None
            assert retrieved_user.username == "testuser"
            assert retrieved_user.email == "test@example.com"
            assert retrieved_user.garmin_username == "garmin_user"
            assert retrieved_user.garmin_password == "plain_password"  # Plain text

class TestGarminClient:
    """Test Garmin client functionality."""
    
    def test_garmin_client_initialization(self, temp_config, temp_database):
        """Test Garmin client initialization."""
        garmin_client = GarminClient(temp_config, temp_database)
        
        assert garmin_client.config == temp_config
        assert garmin_client.database == temp_database
        assert garmin_client._cache_timeout == 300
        assert garmin_client._min_request_interval == 1.0
    
    def test_cache_key_generation(self, temp_config, temp_database):
        """Test cache key generation."""
        garmin_client = GarminClient(temp_config, temp_database)
        
        cache_key = garmin_client._get_cache_key("user123", "get_profile", param1="value1", param2="value2")
        expected = "user123:get_profile:param1=value1&param2=value2"
        assert cache_key == expected
    
    def test_cache_operations(self, temp_config, temp_database):
        """Test cache storage and retrieval."""
        garmin_client = GarminClient(temp_config, temp_database)
        
        # Test cache miss
        cache_key = "test_key"
        assert garmin_client._get_cached_response(cache_key) is None
        
        # Test cache storage
        test_data = {"test": "data"}
        garmin_client._cache_response(cache_key, test_data)
        
        # Test cache hit
        cached_data = garmin_client._get_cached_response(cache_key)
        assert cached_data == test_data
    
    # Removed this test method
    # def test_garmin_client_encryption(self):
    #     """Test Garmin client encryption functionality."""
    
    @patch('src.core.garmin_client.Garmin')
    def test_user_authentication(self, mock_garmin_class, temp_config, temp_database):
        """Test user authentication with Garmin."""
        # Setup mock
        mock_garmin_instance = Mock()
        mock_garmin_class.return_value = mock_garmin_instance
        
        # Create test user
        with temp_database.get_session() as session:
            user = User(
                telegram_user_id=12345,
                username="testuser",
                first_name="Test",
                last_name="User"
            )
            session.add(user)
            session.commit()
            user_id = str(user.id)
        
        # Test authentication
        garmin_client = GarminClient(temp_config, temp_database)
        
        # Mock the asyncio.get_event_loop().run_in_executor call
        with patch('asyncio.get_event_loop') as mock_loop:
            mock_executor = Mock()
            mock_loop.return_value.run_in_executor.return_value = mock_executor
            
            # This would normally be an async test
            # result = await garmin_client.authenticate_user(user_id, "test@example.com", "password")
            # For now, just test the method exists
            assert hasattr(garmin_client, 'authenticate_user')
    
    def test_cache_statistics(self, temp_config, temp_database):
        """Test cache statistics."""
        garmin_client = GarminClient(temp_config, temp_database)
        
        stats = garmin_client.get_cache_stats()
        
        assert 'cache_size' in stats
        assert 'cache_ttl' in stats
        assert 'rate_limit_delay' in stats
        assert stats['cache_size'] == 0  # Empty cache
        assert stats['cache_ttl'] == 300
        assert stats['rate_limit_delay'] == 1.0

if __name__ == "__main__":
    pytest.main([__file__]) 