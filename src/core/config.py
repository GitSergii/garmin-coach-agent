"""
Configuration Management System
===============================

Centralized configuration management for the AI GarminCoach application.
Handles environment variables, validation, and application settings.
"""

import os
import logging
from typing import Optional, Dict, Any
from pathlib import Path
from dataclasses import dataclass, field
from dotenv import load_dotenv


@dataclass
class DatabaseConfig:
    """Database configuration settings."""
    host: str
    port: int
    name: str
    user: str
    password: str
    pool_size: int = 5
    max_overflow: int = 10
    pool_timeout: int = 30
    pool_recycle: int = 3600
    echo: bool = False
    
    @property
    def url(self) -> str:
        """Get database URL."""
        if self.host.endswith('.db') or self.host.endswith('.sqlite'):
            # SQLite database
            return f"sqlite:///{self.host}"
        else:
            # PostgreSQL database
            return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}"


@dataclass
class GoogleCloudConfig:
    """Google Cloud configuration settings."""
    project_id: str
    location: str = "us-central1"
    credentials_path: Optional[str] = None
    api_key: Optional[str] = None


@dataclass
class TelegramConfig:
    """Telegram bot configuration settings."""
    bot_token: str
    webhook_url: Optional[str] = None
    webhook_secret: Optional[str] = None
    owner_user_id: Optional[int] = None
    owner_chat_id: Optional[int] = None
    bind_on_first_start: bool = True
    unauthorized_repo_url: str = "https://github.com/GitSergii/Garmin-Coach"
    max_message_length: int = 4096
    max_connections: int = 40
    allowed_updates: list = field(default_factory=lambda: ["message", "callback_query"])


@dataclass
class SecurityConfig:
    """Security configuration settings."""
    secret_key: str
    token_expires_hours: int = 24
    max_login_attempts: int = 5
    lockout_duration_minutes: int = 15


@dataclass
class FeatureFlags:
    """Feature flag configuration."""
    enable_caching: bool = True
    enable_charts: bool = True
    enable_detailed_logging: bool = True
    enable_cost_monitoring: bool = True
    enable_user_analytics: bool = True
    enable_nl2sql: bool = False


@dataclass
class CostManagementConfig:
    """Cost management configuration."""
    max_daily_api_calls: int = 1000
    max_monthly_cost_usd: float = 50.0
    cache_ttl_hours: int = 24
    enable_cost_alerts: bool = True
    cost_alert_threshold: float = 0.8  # 80% of monthly budget


@dataclass
class ApplicationConfig:
    """Application-specific configuration."""
    env: str = "development"
    debug: bool = False
    log_level: str = "INFO"
    timezone: str = "UTC"
    data_retention_days: int = 90
    max_conversation_history: int = 100


class Config:
    """
    Main configuration class that manages all application settings.
    
    This class loads configuration from environment variables and provides
    validated, typed access to all configuration values.
    """
    
    def __init__(self, env_file: Optional[str] = None):
        """
        Initialize configuration.
        
        Args:
            env_file: Optional path to .env file. If not provided, looks for .env in current directory.
        """
        self._load_environment(env_file)
        self._initialize_configs()
        self._validate_config()
        self._setup_logging()
    
    def _load_environment(self, env_file: Optional[str] = None):
        """Load environment variables from .env file."""
        if env_file:
            env_path = Path(env_file)
        else:
            env_path = Path(".env")
        
        if env_path.exists():
            load_dotenv(env_path, override=True)  # Override existing environment variables
            logging.info(f"Loaded environment variables from {env_path}")
        else:
            logging.warning(f"No .env file found at {env_path}")
    
    def _initialize_configs(self):
        """Initialize all configuration objects."""
        def _parse_optional_int(value: Optional[str]) -> Optional[int]:
            if value is None or value == "":
                return None
            return int(value)
        
        # Database Configuration
        self.database = DatabaseConfig(
            host=os.getenv("DB_HOST", "localhost"),
            port=int(os.getenv("DB_PORT", "5432")),
            name=os.getenv("DB_NAME", "ai_garmin_coach"),
            user=os.getenv("DB_USER", "dev_user"),
            password=os.getenv("DB_PASSWORD", ""),
            pool_size=int(os.getenv("DB_POOL_SIZE", "5")),
            max_overflow=int(os.getenv("DB_MAX_OVERFLOW", "10")),
            pool_timeout=int(os.getenv("DB_POOL_TIMEOUT", "30")),
            pool_recycle=int(os.getenv("DB_POOL_RECYCLE", "3600")),
            echo=os.getenv("DB_ECHO", "false").lower() == "true",
        )
        
        # Google Cloud Configuration
        self.google_cloud = GoogleCloudConfig(
            project_id=os.getenv("GOOGLE_CLOUD_PROJECT", ""),
            location=os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1"),
            credentials_path=os.getenv("GOOGLE_APPLICATION_CREDENTIALS"),
            api_key=os.getenv("GOOGLE_API_KEY")
        )
        
        # Telegram Configuration
        self.telegram = TelegramConfig(
            bot_token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
            webhook_url=os.getenv("TELEGRAM_WEBHOOK_URL"),
            webhook_secret=os.getenv("TELEGRAM_WEBHOOK_SECRET"),
            owner_user_id=_parse_optional_int(os.getenv("TELEGRAM_OWNER_USER_ID")),
            owner_chat_id=_parse_optional_int(os.getenv("TELEGRAM_OWNER_CHAT_ID")),
            bind_on_first_start=os.getenv("TELEGRAM_BIND_ON_FIRST_START", "true").lower() == "true",
            unauthorized_repo_url=os.getenv(
                "TELEGRAM_UNAUTHORIZED_REPO_URL",
                "https://github.com/GitSergii/Garmin-Coach"
            ),
            max_message_length=int(os.getenv("TELEGRAM_MAX_MESSAGE_LENGTH", "4096")),
            max_connections=int(os.getenv("TELEGRAM_MAX_CONNECTIONS", "40"))
        )
        
        # Security Configuration
        self.security = SecurityConfig(
            secret_key=os.getenv("SECRET_KEY", "dev-secret-key"),
            token_expires_hours=int(os.getenv("TOKEN_EXPIRES_HOURS", "24")),
            max_login_attempts=int(os.getenv("MAX_LOGIN_ATTEMPTS", "5")),
            lockout_duration_minutes=int(os.getenv("LOCKOUT_DURATION_MINUTES", "15")),
        )
        
        # Feature Flags
        self.features = FeatureFlags(
            enable_caching=os.getenv("ENABLE_CACHING", "true").lower() == "true",
            enable_charts=os.getenv("ENABLE_CHARTS", "true").lower() == "true",
            enable_detailed_logging=os.getenv("ENABLE_DETAILED_LOGGING", "true").lower() == "true",
            enable_cost_monitoring=os.getenv("ENABLE_COST_MONITORING", "true").lower() == "true",
            enable_user_analytics=os.getenv("ENABLE_USER_ANALYTICS", "true").lower() == "true",
            enable_nl2sql=os.getenv("ENABLE_NL2SQL", "true").lower() == "true",
        )
        
        # Cost Management
        self.cost_management = CostManagementConfig(
            max_daily_api_calls=int(os.getenv("MAX_DAILY_API_CALLS", "1000")),
            max_monthly_cost_usd=float(os.getenv("MAX_MONTHLY_COST_USD", "50.0")),
            cache_ttl_hours=int(os.getenv("CACHE_TTL_HOURS", "24")),
            enable_cost_alerts=os.getenv("ENABLE_COST_ALERTS", "true").lower() == "true",
            cost_alert_threshold=float(os.getenv("COST_ALERT_THRESHOLD", "0.8"))
        )
        
        # Application Configuration
        self.app = ApplicationConfig(
            env=os.getenv("APP_ENV", "development"),
            debug=os.getenv("APP_DEBUG", "false").lower() == "true",
            log_level=os.getenv("APP_LOG_LEVEL", "INFO"),
            timezone=os.getenv("APP_TIMEZONE", "UTC"),
            data_retention_days=int(os.getenv("DATA_RETENTION_DAYS", "90")),
            max_conversation_history=int(os.getenv("MAX_CONVERSATION_HISTORY", "100"))
        )
    
    def _validate_config(self):
        """Validate required configuration values."""
        required_configs = [
            ("GOOGLE_API_KEY", self.google_cloud.api_key),
            ("TELEGRAM_BOT_TOKEN", self.telegram.bot_token),
            ("GOOGLE_CLOUD_PROJECT", self.google_cloud.project_id),
        ]
        
        missing_configs = []
        for config_name, config_value in required_configs:
            if not config_value:
                missing_configs.append(config_name)
        
        if missing_configs:
            raise ValueError(f"Missing required configuration: {', '.join(missing_configs)}")
        
        # Validate database URL format
        if not self.database.url.startswith(("postgresql://", "postgres://", "sqlite:///")):
            raise ValueError("DATABASE_URL must be a PostgreSQL or SQLite connection string")
        
        # Validate Google Cloud project ID format
        if not self.google_cloud.project_id.replace("-", "").replace("_", "").isalnum():
            raise ValueError("GOOGLE_CLOUD_PROJECT must be a valid GCP project ID")
        
        logging.info("Configuration validation passed")
    
    def _setup_logging(self):
        """Setup logging configuration."""
        log_level = getattr(logging, self.app.log_level.upper(), logging.INFO)
        
        # Configure root logger
        logging.basicConfig(
            level=log_level,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.StreamHandler(),
                logging.FileHandler('ai_garmin_coach.log') if self.app.env == "production" else logging.NullHandler()
            ]
        )
        
        # Set specific logger levels
        if self.app.env == "development":
            logging.getLogger("sqlalchemy.engine").setLevel(logging.INFO if self.database.echo else logging.WARNING)
            logging.getLogger("telegram").setLevel(logging.INFO)
        else:
            logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
            logging.getLogger("telegram").setLevel(logging.WARNING)
    
    # Removed this method
    # def get_encryption_key(self) -> Fernet:
    #     """Get Fernet encryption instance."""
    #     return Fernet(self.security.encryption_key)
    
    def is_development(self) -> bool:
        """Check if running in development mode."""
        return self.app.env == "development"
    
    def is_production(self) -> bool:
        """Check if running in production mode."""
        return self.app.env == "production"
    
    def get_database_url(self) -> str:
        """Get database connection URL."""
        return self.database.url
    
    def get_config_summary(self) -> Dict[str, Any]:
        """Get a summary of current configuration (safe for logging)."""
        return {
            "environment": self.app.env,
            "debug": self.app.debug,
            "log_level": self.app.log_level,
            "database_host": self.database.host,
            "database_port": self.database.port,
            "database_name": self.database.name,
            "gcp_project": self.google_cloud.project_id,
            "gcp_location": self.google_cloud.location,
            "features": {
                "caching": self.features.enable_caching,
                "charts": self.features.enable_charts,
                "monitoring": self.features.enable_cost_monitoring,
            },
            "cost_limits": {
                "daily_api_calls": self.cost_management.max_daily_api_calls,
                "monthly_budget": self.cost_management.max_monthly_cost_usd,
                "cache_ttl": self.cost_management.cache_ttl_hours,
            }
        }
    
    def __repr__(self) -> str:
        """String representation of configuration."""
        return f"Config(env={self.app.env}, debug={self.app.debug})"


# Global configuration instance
config = None

def get_config(env_file: Optional[str] = None) -> Config:
    """
    Get the global configuration instance.
    
    Args:
        env_file: Optional path to .env file
        
    Returns:
        Config instance
    """
    global config
    if config is None:
        config = Config(env_file)
    return config


def init_config(env_file: Optional[str] = None) -> Config:
    """
    Initialize the global configuration.
    
    Args:
        env_file: Optional path to .env file
        
    Returns:
        Config instance
    """
    global config
    config = Config(env_file)
    return config 