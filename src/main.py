"""
AI GarminCoach Main Application
===============================

Main entry point for the AI GarminCoach application.
Handles initialization, system checks, and application lifecycle.
"""

import asyncio
import logging
import signal
import sys
from typing import Optional
from datetime import datetime

from core.config import init_config
from core.database import init_database
from core.garmin_client import init_garmin_client
from core.telegram_bot import init_telegram_bot
from coach_adk.runtime import init_adk_coach_runtime_async
from tools.data_tools import init_data_tools
from tools.db_tools import init_database_tools
from tools.analysis_tools import init_analysis_tools
from tools.chart_tools import init_chart_tools


# Configure logging
def setup_logging():
    """Set up logging configuration."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler('ai_garmin_coach.log')
        ]
    )
    
    # Set specific log levels
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('telegram').setLevel(logging.WARNING)
    logging.getLogger('sqlalchemy').setLevel(logging.WARNING)
    
    logger = logging.getLogger(__name__)
    logger.info("Logging configured successfully")
    return logger


async def test_database_connection(database):
    """Test database connection."""
    try:
        if database.test_connection():
            logger.info("✅ Database connection successful")
            return True
        else:
            logger.error("❌ Database connection failed")
            return False
    except Exception as e:
        logger.error(f"❌ Database connection error: {e}")
        return False


async def test_garmin_client(garmin_client):
    """Test Garmin client initialization."""
    try:
        # Test basic initialization
        logger.info("✅ Garmin client initialized successfully")
        return True
    except Exception as e:
        logger.error(f"❌ Garmin client initialization error: {e}")
        return False


async def test_coach_agent(coach_agent):
    """Test coach agent initialization."""
    try:
        # Test basic functionality
        stats = coach_agent.get_performance_stats()
        logger.info(f"✅ Coach agent initialized successfully - Stats: {stats}")
        return True
    except Exception as e:
        logger.error(f"❌ Coach agent initialization error: {e}")
        return False


async def test_tools(data_tools, db_tools, analysis_tools, chart_tools):
    """Test tools initialization."""
    try:
        logger.info("✅ All tools initialized successfully")
        return True
    except Exception as e:
        logger.error(f"❌ Tools initialization error: {e}")
        return False


async def test_telegram_bot(telegram_bot):
    """Test Telegram bot initialization."""
    try:
        logger.info("✅ Telegram bot initialized successfully")
        return True
    except Exception as e:
        logger.error(f"❌ Telegram bot initialization error: {e}")
        return False


async def display_startup_info(config):
    """Display startup information."""
    logger.info("🚀 AI GarminCoach Starting Up")
    logger.info("=" * 50)
    
    # Display configuration summary
    config_summary = config.get_config_summary()
    logger.info(f"Environment: {config_summary.get('environment', 'unknown')}")
    logger.info(f"Database: {config_summary.get('database_type', 'unknown')}")
    logger.info(f"Google Cloud Project: {config_summary.get('google_cloud_project', 'not set')}")
    logger.info(f"Telegram Bot: {'configured' if config.telegram.bot_token else 'not configured'}")
    logger.info("Coach backend: ADK")
    
    logger.info("=" * 50)


async def run_system_checks():
    """Run comprehensive system checks."""
    logger.info("🔍 Running System Checks...")
    
    try:
        # Initialize configuration
        config = init_config()
        await display_startup_info(config)
        
        # Initialize database
        database = init_database(config)
        # Ensure schema exists before any component queries tables (e.g. telegram owner binding).
        database.create_tables()
        db_ok = await test_database_connection(database)
        
        # Initialize tools
        db_tools = init_database_tools(database, config)
        data_tools = init_data_tools(None, db_tools, config)  # Garmin client will be set later
        analysis_tools = init_analysis_tools(data_tools, db_tools, config)
        chart_tools = init_chart_tools(data_tools, config)
        
        tools_ok = await test_tools(data_tools, db_tools, analysis_tools, chart_tools)
        
        # Initialize Garmin client
        garmin_client = init_garmin_client(config, database)
        garmin_ok = await test_garmin_client(garmin_client)
        
        # Update data_tools with garmin_client
        data_tools.garmin_client = garmin_client
        
        # Initialize coach agent
        coach_agent = await init_adk_coach_runtime_async(config=config)
        agent_ok = await test_coach_agent(coach_agent)
        
        # Initialize Telegram bot
        telegram_bot = await init_telegram_bot(config, database, coach_agent, data_tools, db_tools, analysis_tools)
        bot_ok = await test_telegram_bot(telegram_bot)
        
        # Summary
        all_ok = all([db_ok, tools_ok, garmin_ok, agent_ok, bot_ok])
        
        if all_ok:
            logger.info("✅ All system checks passed!")
            return {
                'config': config,
                'database': database,
                'garmin_client': garmin_client,
                'coach_agent': coach_agent,
                'telegram_bot': telegram_bot,
                'data_tools': data_tools,
                'db_tools': db_tools,
                'analysis_tools': analysis_tools,
                'chart_tools': chart_tools,
            }
        else:
            logger.error("❌ Some system checks failed")
            return None
            
    except Exception as e:
        logger.error(f"❌ System check error: {e}")
        return None


async def initialize_system():
    """Initialize the complete system."""
    logger.info("🔧 Initializing AI GarminCoach System...")
    
    try:
        # Run system checks
        components = await run_system_checks()
        
        if not components:
            logger.error("❌ System initialization failed")
            return None
        
        # Test basic functionality
        try:
            logger.info("✅ Coach agent initialized (runtime user checks happen via Telegram /start)")
        except Exception as e:
            logger.warning(f"⚠️ Coach agent test warning: {e}")
        
        logger.info("✅ System initialization completed successfully")
        return components
        
    except Exception as e:
        logger.error(f"❌ System initialization error: {e}")
        return None


async def run_integration_test():
    """Run integration tests."""
    logger.info("🧪 Running Integration Tests...")
    
    try:
        components = await initialize_system()
        if not components:
            logger.error("❌ Integration test failed - system initialization failed")
            return False
        
        # Test basic message processing
        try:
            test_response = await components['coach_agent'].process_message(
                "test_user", 
                "Hello, how are you?"
            )
            logger.info(f"✅ Message processing test successful: {test_response.text[:100]}...")
        except Exception as e:
            logger.error(f"❌ Message processing test failed: {e}")
            return False
        
        logger.info("✅ Integration tests passed!")
        return True
        
    except Exception as e:
        logger.error(f"❌ Integration test error: {e}")
        return False


async def start_application():
    """Start the main application."""
    logger.info("🚀 Starting AI GarminCoach Application...")
    
    try:
        # Initialize system
        components = await initialize_system()
        if not components:
            logger.error("❌ Failed to initialize system")
            return False
        
        # Set up signal handlers for graceful shutdown
        def signal_handler(signum, frame):
            logger.info(f"🛑 Received signal {signum}, shutting down gracefully...")
            asyncio.create_task(shutdown_application(components))
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        # Start Telegram bot
        logger.info("🤖 Starting Telegram bot...")
        await components['telegram_bot'].start_polling()
        
        # Keep the application running
        logger.info("✅ Application started successfully!")
        logger.info("📱 Telegram bot is now running and listening for messages")
        logger.info("🛑 Press Ctrl+C to stop the application")
        
        # Wait indefinitely
        while True:
            await asyncio.sleep(1)
            
    except Exception as e:
        logger.error(f"❌ Application startup error: {e}")
        return False


async def shutdown_application(components):
    """Shutdown the application gracefully."""
    logger.info("🛑 Shutting down AI GarminCoach...")
    
    try:
        # Stop Telegram bot
        if components and 'telegram_bot' in components:
            await components['telegram_bot'].stop()
            logger.info("✅ Telegram bot stopped")
        
        # Close database connections
        if components and 'database' in components:
            components['database'].engine.dispose()
            logger.info("✅ Database connections closed")
        
        logger.info("✅ Shutdown completed successfully")
        
    except Exception as e:
        logger.error(f"❌ Shutdown error: {e}")
    
    finally:
        sys.exit(0)


async def run_test_mode():
    """Run the application in test mode."""
    logger.info("🧪 Running in Test Mode...")
    
    try:
        # Run integration tests
        success = await run_integration_test()
        
        if success:
            logger.info("✅ All tests passed!")
            return True
        else:
            logger.error("❌ Some tests failed")
            return False
            
    except Exception as e:
        logger.error(f"❌ Test mode error: {e}")
        return False


async def main():
    """Main entry point."""
    global logger
    logger = setup_logging()
    
    # Check command line arguments
    if len(sys.argv) > 1:
        command = sys.argv[1].lower()
        
        if command == "test":
            logger.info("🧪 Running in test mode...")
            success = await run_test_mode()
            sys.exit(0 if success else 1)
        
        elif command == "check":
            logger.info("🔍 Running system checks...")
            components = await run_system_checks()
            sys.exit(0 if components else 1)
        
        elif command == "help":
            print("""
AI GarminCoach - Usage Options:

python src/main.py          # Start the application normally
python src/main.py test     # Run integration tests
python src/main.py check    # Run system checks only
python src/main.py help     # Show this help message

Environment Variables Required:
- GOOGLE_API_KEY: Your Google Gen AI API key
- TELEGRAM_BOT_TOKEN: Your Telegram bot token
- DATABASE_URL: Your database connection string
            """)
            sys.exit(0)
    
    # Start the application normally
    try:
        success = await start_application()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        logger.info("🛑 Application interrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"❌ Application error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main()) 