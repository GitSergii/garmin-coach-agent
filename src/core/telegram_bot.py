"""
Telegram Bot Integration
========================

This module provides Telegram bot integration for the AI GarminCoach system.
Handles user interactions, message processing, and bot commands.
"""

import asyncio
import logging
from typing import Dict, List, Any, Optional, Callable
from datetime import datetime, timedelta
import json
import uuid
from pathlib import Path
from types import SimpleNamespace

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters, ConversationHandler, ApplicationHandlerStop
)
from telegram.constants import ParseMode

from core.config import Config
from core.database import Database, User
from tools.data_tools import DataTools
from tools.db_tools import DatabaseTools
from tools.analysis_tools import AnalysisTools


logger = logging.getLogger(__name__)

# Conversation states
SETUP_GARMIN_EMAIL, SETUP_GARMIN_PASSWORD, SETUP_GOALS, SETUP_PREFERENCES = range(4)


class TelegramBot:
    """
    Telegram bot for AI GarminCoach system.
    
    Features:
    - User registration and authentication
    - Garmin account setup
    - Natural language interaction with coach agent
    - Quick commands for common actions
    - Settings and preferences management
    - Rich formatting and interactive elements
    """
    
    def __init__(self, config: Config, database: Database, coach_agent: Any,
                 data_tools: DataTools, db_tools: DatabaseTools, analysis_tools: AnalysisTools):
        """Initialize the Telegram bot."""
        self.config = config
        self.database = database
        self.coach_agent = coach_agent
        self.data_tools = data_tools
        self.db_tools = db_tools
        self.analysis_tools = analysis_tools
        self.logger = logging.getLogger(__name__)
        
        # Bot application
        self.application = None
        
        # User session management
        self.active_users: Dict[int, str] = {}  # telegram_user_id -> user_id
        self.user_states: Dict[int, Dict[str, Any]] = {}  # telegram_user_id -> state

        # Single-owner access control (env values can override DB settings)
        self.owner_user_id: Optional[int] = self.config.telegram.owner_user_id
        self.owner_chat_id: Optional[int] = self.config.telegram.owner_chat_id
        
        # Performance tracking
        self.message_count = 0
        self.start_time = datetime.now()
    
    async def initialize(self):
        """Initialize the Telegram bot application."""
        try:
            # Create application
            self.application = Application.builder().token(self.config.telegram.bot_token).build()
            
            # Register handlers
            self._register_handlers()
            self._load_owner_binding()
            
            self.logger.info("✅ Telegram bot initialized successfully")
            
        except Exception as e:
            self.logger.error(f"❌ Failed to initialize Telegram bot: {e}")
            raise

    def _load_owner_binding(self):
        """Load owner binding from DB when not provided via env."""
        if self.owner_user_id is not None and self.owner_chat_id is not None:
            return

        binding = self.database.get_telegram_owner_binding()
        if binding:
            if self.owner_user_id is None:
                self.owner_user_id = binding["user_id"]
            if self.owner_chat_id is None:
                self.owner_chat_id = binding["chat_id"]
    
    def _register_handlers(self):
        """Register all bot handlers."""
        # Command handlers
        self.application.add_handler(CommandHandler("start", self.handle_start))
        self.application.add_handler(CommandHandler("help", self.handle_help))
        self.application.add_handler(CommandHandler("stats", self.handle_stats))
        self.application.add_handler(CommandHandler("today", self.handle_today))
        self.application.add_handler(CommandHandler("goals", self.handle_goals))
        self.application.add_handler(CommandHandler("settings", self.handle_settings))
        self.application.add_handler(CommandHandler("sync", self.handle_sync))
        self.application.add_handler(CommandHandler("trends", self.handle_trends))
        
        # Conversation handler for setup
        setup_handler = ConversationHandler(
            entry_points=[CommandHandler("setup", self.handle_setup)],
            states={
                SETUP_GARMIN_EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_garmin_email)],
                SETUP_GARMIN_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_garmin_password)],
                SETUP_GOALS: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_goals_setup)],
                SETUP_PREFERENCES: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_preferences_setup)]
            },
            fallbacks=[CommandHandler("cancel", self.handle_cancel)]
        )
        self.application.add_handler(setup_handler)
        
        # Callback query handler for inline keyboards
        self.application.add_handler(CallbackQueryHandler(self.handle_callback_query))
        
        # Message handler for natural language queries
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
        
        # Error handler
        self.application.add_error_handler(self.handle_error)
    
    # Command Handlers
    
    async def handle_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command."""
        if not await self._authorize_update(update, allow_first_bind=True):
            return

        telegram_user_id = update.effective_user.id
        username = update.effective_user.username or f"user_{telegram_user_id}"
        first_name = update.effective_user.first_name or "Friend"
        
        self.logger.info(f"User {telegram_user_id} started the bot")
        
        # Check if user exists
        user = await self._get_or_create_user(telegram_user_id, username, first_name)
        
        if user:
            # User exists, welcome back
            welcome_message = f"Welcome back, {first_name}! 👋\n\n"
            welcome_message += "I'm your AI fitness coach. I can help you:\n"
            welcome_message += "• Track your fitness progress\n"
            welcome_message += "• Analyze your Garmin data\n"
            welcome_message += "• Set and monitor goals\n"
            welcome_message += "• Provide personalized insights\n\n"
            welcome_message += "What would you like to know about your fitness today?"
            
            # Add quick action buttons
            keyboard = [
                [InlineKeyboardButton("📊 Today's Summary", callback_data="today_summary")],
                [InlineKeyboardButton("🎯 My Goals", callback_data="view_goals")],
                [InlineKeyboardButton("📈 Trends", callback_data="view_trends")],
                [InlineKeyboardButton("⚙️ Settings", callback_data="view_settings")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(welcome_message, reply_markup=reply_markup)
        else:
            # New user, start setup
            welcome_message = f"Hi {first_name}! 👋 Welcome to AI GarminCoach!\n\n"
            welcome_message += "I'm your personal AI fitness coach. I'll help you track your progress, "
            welcome_message += "analyze your Garmin data, and reach your fitness goals.\n\n"
            welcome_message += "To get started, I'll need to connect to your Garmin account. "
            welcome_message += "Use /setup to begin the setup process.\n\n"
            welcome_message += "Don't worry - your data is secure and only used to provide personalized coaching! 🔒"
            
            await update.message.reply_text(welcome_message)
    
    async def handle_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command."""
        if not await self._authorize_update(update):
            return

        help_message = """
🤖 **AI GarminCoach Commands**

**Basic Commands:**
• /start - Start or restart the bot
• /help - Show this help message
• /setup - Set up your Garmin account and preferences

**Fitness Commands:**
• /today - Get today's fitness summary
• /stats - View your fitness statistics
• /goals - Manage your fitness goals
• /trends - View fitness trends and analysis
• /sync - Sync your latest Garmin data

**Settings:**
• /settings - Manage your preferences

**Natural Language:**
You can also just chat with me naturally! Try asking:
• "How did I sleep last night?"
• "What's my heart rate trend?"
• "How am I doing with my step goal?"
• "Show me my running progress"

I'm here to help you reach your fitness goals! 💪
        """
        
        await update.message.reply_text(help_message, parse_mode=ParseMode.MARKDOWN)
    
    async def handle_today(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /today command."""
        if not await self._authorize_update(update):
            return

        telegram_user_id = update.effective_user.id
        user_id = await self._get_user_id(telegram_user_id)
        
        if not user_id:
            await update.message.reply_text("Please use /setup to configure your account first.")
            return
        
        await update.message.reply_text("📊 Getting your daily summary...")
        
        try:
            # Get today's data
            today_data = await self.data_tools.fetch_daily_summary(user_id, datetime.now())
            
            if not today_data:
                await update.message.reply_text(
                    "No data available for today yet. Try syncing your Garmin device or check back later."
                )
                return
            
            # Format the summary
            summary = self._format_daily_summary(today_data)
            
            # Add quick actions
            keyboard = [
                [InlineKeyboardButton("📈 View Trends", callback_data="view_trends")],
                [InlineKeyboardButton("🎯 Check Goals", callback_data="view_goals")],
                [InlineKeyboardButton("🔄 Sync Data", callback_data="sync_data")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(summary, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
            
        except Exception as e:
            self.logger.error(f"Error handling today command: {e}")
            await update.message.reply_text("Sorry, I encountered an error while getting your daily summary. Please try again later.")
    
    async def handle_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /stats command."""
        if not await self._authorize_update(update):
            return

        telegram_user_id = update.effective_user.id
        user_id = await self._get_user_id(telegram_user_id)
        
        if not user_id:
            await update.message.reply_text("Please use /setup to configure your account first.")
            return
        
        await update.message.reply_text("📊 Calculating your fitness statistics...")
        
        try:
            # Get fitness score
            fitness_score = await self.data_tools.calculate_fitness_score(user_id)
            
            if "error" in fitness_score:
                await update.message.reply_text(f"Unable to calculate fitness score: {fitness_score['error']}")
                return
            
            # Format the stats
            stats_message = self._format_fitness_stats(fitness_score)
            
            await update.message.reply_text(stats_message, parse_mode=ParseMode.MARKDOWN)
            
        except Exception as e:
            self.logger.error(f"Error handling stats command: {e}")
            await update.message.reply_text("Sorry, I encountered an error while calculating your statistics. Please try again later.")
    
    async def handle_goals(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /goals command."""
        if not await self._authorize_update(update):
            return

        telegram_user_id = update.effective_user.id
        user_id = await self._get_user_id(telegram_user_id)
        
        if not user_id:
            await update.message.reply_text("Please use /setup to configure your account first.")
            return
        
        try:
            # Get user profile with goals
            profile = await self.db_tools.get_user_profile(user_id)
            
            if not profile or not profile.get("goals"):
                await update.message.reply_text("You don't have any goals set yet. Let's create some! What fitness goal would you like to work on?")
                return
            
            # Format goals
            goals_message = self._format_goals(profile["goals"])
            
            # Add action buttons
            keyboard = [
                [InlineKeyboardButton("📊 Goal Progress", callback_data="goal_progress")],
                [InlineKeyboardButton("➕ Add Goal", callback_data="add_goal")],
                [InlineKeyboardButton("⚙️ Manage Goals", callback_data="manage_goals")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(goals_message, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
            
        except Exception as e:
            self.logger.error(f"Error handling goals command: {e}")
            await update.message.reply_text("Sorry, I encountered an error while retrieving your goals. Please try again later.")
    
    async def handle_settings(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /settings command."""
        if not await self._authorize_update(update):
            return

        telegram_user_id = update.effective_user.id
        user_id = await self._get_user_id(telegram_user_id)
        
        if not user_id:
            await update.message.reply_text("Please use /setup to configure your account first.")
            return
        
        try:
            # Get user profile
            profile = await self.db_tools.get_user_profile(user_id)
            
            if not profile:
                await update.message.reply_text("Unable to retrieve your settings. Please try /setup first.")
                return
            
            # Format settings
            settings_message = self._format_settings(profile["settings"])
            
            # Add action buttons
            keyboard = [
                [InlineKeyboardButton("🎨 Coaching Style", callback_data="change_coaching_style")],
                [InlineKeyboardButton("📊 Preferred Metrics", callback_data="change_metrics")],
                [InlineKeyboardButton("🔔 Notifications", callback_data="change_notifications")],
                [InlineKeyboardButton("🌐 Units & Display", callback_data="change_display")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(settings_message, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
            
        except Exception as e:
            self.logger.error(f"Error handling settings command: {e}")
            await update.message.reply_text("Sorry, I encountered an error while retrieving your settings. Please try again later.")
    
    async def handle_sync(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /sync command - runs the sync_garmin_data.py script."""
        if not await self._authorize_update(update):
            return

        telegram_user_id = update.effective_user.id
        user_id = await self._get_user_id(telegram_user_id)
        
        if not user_id:
            await update.message.reply_text("Please use /setup to configure your account first.")
            return
        
        await update.message.reply_text("🔄 Starting Garmin data sync...\n\nThis may take a few minutes to fetch your latest data.")
        
        try:
            # Run the sync script asynchronously
            import subprocess
            import sys
            import os
            
            # Get the path to the sync script
            script_path = os.path.join(os.getcwd(), "sync_garmin_data.py")
            
            # Run the sync script
            process = await asyncio.create_subprocess_exec(
                sys.executable, script_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                # Success - parse the output to get summary
                output = stdout.decode('utf-8')
                
                # Extract summary information from the output
                summary_lines = []
                for line in output.split('\n'):
                    if any(keyword in line for keyword in ['synced', 'Daily summaries', 'Activities', 'Heart rate']):
                        summary_lines.append(line.strip())
                
                if summary_lines:
                    summary = "✅ **Sync completed successfully!**\n\n"
                    summary += "**Data Summary:**\n"
                    for line in summary_lines[-3:]:  # Show last 3 summary lines
                        summary += f"• {line}\n"
                else:
                    summary = "✅ **Sync completed successfully!**\n\nYour latest Garmin data has been synced."
                
                await update.message.reply_text(summary, parse_mode=ParseMode.MARKDOWN)
                
            else:
                # Error occurred
                error_output = stderr.decode('utf-8')
                self.logger.error(f"Sync script failed: {error_output}")
                
                await update.message.reply_text(
                    "❌ **Sync failed!**\n\n"
                    "There was an error during the sync process. This could be due to:\n"
                    "• Network connectivity issues\n"
                    "• Garmin service temporarily unavailable\n"
                    "• Authentication problems\n\n"
                    "Please try again in a few minutes or check your Garmin credentials."
                )
            
        except Exception as e:
            self.logger.error(f"Error handling sync command: {e}")
            await update.message.reply_text(
                "❌ **Sync error!**\n\n"
                "I encountered an unexpected error during the sync process. "
                "Please try again later or contact support if the problem persists."
            )
    
    async def handle_trends(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /trends command."""
        if not await self._authorize_update(update):
            return

        telegram_user_id = update.effective_user.id
        user_id = await self._get_user_id(telegram_user_id)
        
        if not user_id:
            await update.message.reply_text("Please use /setup to configure your account first.")
            return
        
        await update.message.reply_text("📈 Analyzing your fitness trends...")
        
        try:
            # Get trend analysis
            trends = await self.analysis_tools.analyze_multi_metric_trends(user_id, 30)
            
            if "error" in trends:
                await update.message.reply_text(f"Unable to analyze trends: {trends['error']}")
                return
            
            # Format trends
            trends_message = self._format_trends(trends)
            
            await update.message.reply_text(trends_message, parse_mode=ParseMode.MARKDOWN)
            
        except Exception as e:
            self.logger.error(f"Error handling trends command: {e}")
            await update.message.reply_text("Sorry, I encountered an error while analyzing your trends. Please try again later.")
    
    # Setup Conversation Handlers
    
    async def handle_setup(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /setup command to start user setup."""
        if not await self._authorize_update(update):
            return ConversationHandler.END

        telegram_user_id = update.effective_user.id
        
        # Initialize user state
        self.user_states[telegram_user_id] = {}
        
        setup_message = """
🔧 **Account Setup**

To provide personalized coaching, I need to connect to your Garmin account.

**What I'll ask for:**
1. Your Garmin Connect email
2. Your Garmin Connect password
3. Your fitness goals
4. Your coaching preferences

**Privacy & Security:**
• Your credentials are encrypted and stored securely
• Data is only used for coaching purposes
• You can disconnect at any time

Ready to get started? Please enter your Garmin Connect email address:
        """
        
        await update.message.reply_text(setup_message, parse_mode=ParseMode.MARKDOWN)
        return SETUP_GARMIN_EMAIL
    
    async def handle_garmin_email(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle Garmin email input."""
        if not await self._authorize_update(update):
            return ConversationHandler.END

        telegram_user_id = update.effective_user.id
        email = update.message.text.strip()
        
        # Basic email validation
        if "@" not in email or "." not in email:
            await update.message.reply_text("Please enter a valid email address:")
            return SETUP_GARMIN_EMAIL
        
        # Store email
        self.user_states[telegram_user_id]["garmin_email"] = email
        
        await update.message.reply_text(
            "✅ Email saved!\n\n"
            "Now, please enter your Garmin Connect password:\n"
            "⚠️ This message will be deleted for security."
        )
        return SETUP_GARMIN_PASSWORD
    
    async def handle_garmin_password(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle Garmin password input."""
        if not await self._authorize_update(update):
            return ConversationHandler.END

        telegram_user_id = update.effective_user.id
        password = update.message.text.strip()
        
        # Delete the password message immediately
        try:
            await update.message.delete()
        except:
            pass
        
        # Store password
        self.user_states[telegram_user_id]["garmin_password"] = password
        
        # Test Garmin authentication
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="🔐 Testing Garmin connection..."
        )
        
        try:
            user_id = await self._get_user_id(telegram_user_id)
            if user_id:
                # Test authentication
                success = await self.data_tools.garmin_client.authenticate_user(
                    user_id, 
                    self.user_states[telegram_user_id]["garmin_email"],
                    password
                )
                
                if success:
                    await context.bot.send_message(
                        chat_id=update.effective_chat.id,
                        text="✅ Garmin connection successful!\n\n"
                             "Now, let's set up your fitness goals. What's your main fitness objective?\n"
                             "Examples: 'Walk 10,000 steps daily', 'Run 5K in under 25 minutes', 'Lose 10 pounds'"
                    )
                    return SETUP_GOALS
                else:
                    await context.bot.send_message(
                        chat_id=update.effective_chat.id,
                        text="❌ Garmin authentication failed. Please check your credentials and try again.\n\n"
                             "Enter your Garmin Connect email:"
                    )
                    return SETUP_GARMIN_EMAIL
            else:
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text="❌ Error creating user account. Please try /setup again."
                )
                return ConversationHandler.END
                
        except Exception as e:
            self.logger.error(f"Error during Garmin authentication: {e}")
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="❌ Error testing Garmin connection. Please try again later."
            )
            return ConversationHandler.END
    
    async def handle_goals_setup(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle goals setup."""
        if not await self._authorize_update(update):
            return ConversationHandler.END

        telegram_user_id = update.effective_user.id
        goals_text = update.message.text.strip()
        
        # Store goals
        self.user_states[telegram_user_id]["goals"] = goals_text
        
        preferences_message = """
🎯 Goals saved!

Now let's set your coaching preferences:

**Coaching Style Options:**
• **Motivational** - High energy, encouraging, celebrate every win
• **Analytical** - Data-focused, detailed insights, scientific approach  
• **Balanced** - Mix of motivation and analysis (recommended)

Which coaching style do you prefer?
        """
        
        await update.message.reply_text(preferences_message, parse_mode=ParseMode.MARKDOWN)
        return SETUP_PREFERENCES
    
    async def handle_preferences_setup(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle preferences setup."""
        if not await self._authorize_update(update):
            return ConversationHandler.END

        telegram_user_id = update.effective_user.id
        preference_text = update.message.text.strip().lower()
        
        # Map user input to coaching style
        coaching_style = "balanced"
        if "motivational" in preference_text or "motivation" in preference_text:
            coaching_style = "motivational"
        elif "analytical" in preference_text or "analysis" in preference_text or "data" in preference_text:
            coaching_style = "analytical"
        
        # Store preferences
        self.user_states[telegram_user_id]["coaching_style"] = coaching_style
        
        # Save all settings
        try:
            user_id = await self._get_user_id(telegram_user_id)
            if user_id:
                # Update user settings
                await self.db_tools.update_user_settings(user_id, {
                    "coaching_style": coaching_style,
                    "preferred_metrics": ["steps", "heart_rate", "sleep", "calories_burned"]
                })
                
                # Create initial goal if specified
                goals_text = self.user_states[telegram_user_id].get("goals", "")
                if goals_text:
                    await self.db_tools.create_user_goal(user_id, {
                        "goal_type": "steps",  # Default to steps
                        "goal_name": goals_text,
                        "target_value": 10000,  # Default target
                        "unit": "steps"
                    })
                
                completion_message = f"""
🎉 **Setup Complete!**

Your AI GarminCoach is ready! Here's what I've configured:

✅ Garmin account connected
✅ Coaching style: {coaching_style.title()}
✅ Initial goals set
✅ Preferences saved

**What's next?**
• I'll sync your Garmin data automatically
• Ask me anything about your fitness
• Use /today to see your daily summary
• Check /goals to manage your objectives

Ready to start your fitness journey? Try asking me "How did I do today?" or "What's my recent progress?"

Let's get fit together! 💪
                """
                
                await update.message.reply_text(completion_message, parse_mode=ParseMode.MARKDOWN)
                
                # Start a conversation with the coach
                welcome_response = await self.coach_agent.start_conversation(user_id)
                await update.message.reply_text(welcome_response)
                
        except Exception as e:
            self.logger.error(f"Error completing setup: {e}")
            await update.message.reply_text("❌ Error completing setup. Please try /setup again.")
        
        # Clear user state
        if telegram_user_id in self.user_states:
            del self.user_states[telegram_user_id]
        
        return ConversationHandler.END
    
    async def handle_cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle setup cancellation."""
        if not await self._authorize_update(update):
            return ConversationHandler.END

        telegram_user_id = update.effective_user.id
        
        # Clear user state
        if telegram_user_id in self.user_states:
            del self.user_states[telegram_user_id]
        
        await update.message.reply_text("Setup cancelled. You can start again anytime with /setup.")
        return ConversationHandler.END
    
    # Message and Callback Handlers
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle natural language messages."""
        if not await self._authorize_update(update, allow_first_bind=True):
            return

        telegram_user_id = update.effective_user.id
        user_id = await self._get_user_id(telegram_user_id)

        if not user_id:
            username = update.effective_user.username or f"user_{telegram_user_id}"
            first_name = update.effective_user.first_name or "Friend"
            user = await self._get_or_create_user(telegram_user_id, username, first_name)
            if not user:
                await update.message.reply_text(
                    "I couldn't initialize your local profile right now. Please try again."
                )
                return
            user_id = str(user.id)
        
        message_text = update.message.text
        self.message_count += 1
        
        # Show typing indicator
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
        
        try:
            # Process message with coach agent
            response = await self.coach_agent.process_message(user_id, message_text)
            
            # Clean response text to avoid parsing errors
            clean_response = self._clean_response_text(response.text)
            
            # Send response without markdown to avoid parsing errors
            await update.message.reply_text(clean_response)

            # Send generated chart image when available.
            await self._send_chart_if_available(update, response)
            
            # Log API usage
            await self.db_tools.log_api_usage(
                user_id=user_id,
                api_service="telegram",
                feature_used="natural_language_query",
                response_time_ms=response.response_time_ms,
                success=True,
                tokens_used=response.tokens_used
            )
            
        except Exception as e:
            self.logger.error(f"Error handling message: {e}")
            await update.message.reply_text("Sorry, I encountered an error processing your message. Please try again or use a specific command.")

    async def _send_chart_if_available(self, update: Update, response: Any) -> None:
        """Send a generated chart image when response contains chart metadata."""
        if not getattr(response, "has_charts", False):
            return

        chart_data = getattr(response, "chart_data", None) or {}
        chart_path = chart_data.get("chart_path")
        if not chart_path:
            self.logger.warning("Chart response missing chart_path metadata")
            return

        chart_file = Path(chart_path)
        if not chart_file.exists():
            self.logger.warning(f"Chart file does not exist: {chart_file}")
            return

        caption = chart_data.get("caption", "Generated chart")
        try:
            with chart_file.open("rb") as photo:
                await update.message.reply_photo(photo=photo, caption=caption)
        except Exception as e:
            self.logger.error(f"Failed to send chart image {chart_file}: {e}")
    
    def _clean_response_text(self, text: str) -> str:
        """Clean response text to avoid Telegram parsing errors."""
        if not text:
            return "I'm sorry, I couldn't generate a response. Please try again."
        
        # Remove or escape problematic characters
        cleaned = text
        
        # Strip markdown formatting characters
        cleaned = cleaned.replace("*", "")
        cleaned = cleaned.replace("_", "")
        cleaned = cleaned.replace("`", "'")
        cleaned = cleaned.replace("```", "")
        
        # Limit length to avoid Telegram limits
        if len(cleaned) > 4000:
            cleaned = cleaned[:4000] + "..."
        
        return cleaned
    
    async def handle_callback_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle callback queries from inline keyboards."""
        if not await self._authorize_update(update):
            return

        query = update.callback_query
        await query.answer()
        
        telegram_user_id = query.from_user.id
        user_id = await self._get_user_id(telegram_user_id)
        
        if not user_id:
            await query.message.reply_text("Please use /setup to configure your account first.")
            return
        
        callback_data = query.data
        callback_update = SimpleNamespace(
            effective_user=query.from_user,
            effective_chat=query.message.chat if query.message else None,
            message=query.message,
            effective_message=query.message,
            callback_query=query,
        )
        
        try:
            if callback_data == "today_summary":
                await self.handle_today(callback_update, context)
            elif callback_data == "view_goals":
                await self.handle_goals(callback_update, context)
            elif callback_data == "view_trends":
                await self.handle_trends(callback_update, context)
            elif callback_data == "view_settings":
                await self.handle_settings(callback_update, context)
            elif callback_data == "sync_data":
                await self.handle_sync(callback_update, context)
            # Add more callback handlers as needed
            
        except Exception as e:
            self.logger.error(f"Error handling callback query: {e}")
            await query.message.reply_text("Sorry, I encountered an error processing your request.")
    
    async def handle_error(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle errors."""
        self.logger.error(f"Telegram bot error: {context.error}")
        
        if update and update.effective_message:
            await update.effective_message.reply_text(
                "Sorry, I encountered an unexpected error. Please try again later."
            )
    
    # Helper Methods

    async def _authorize_update(self, update: Update, allow_first_bind: bool = False) -> bool:
        """Authorize incoming updates using single-owner policy."""
        user = update.effective_user
        chat = update.effective_chat

        if not user or not chat:
            return False

        # Personal bot must only run in private chats.
        if chat.type != "private":
            await self._reply_unauthorized(update)
            return False

        telegram_user_id = user.id
        chat_id = chat.id

        if self.owner_user_id is None:
            if allow_first_bind and self.config.telegram.bind_on_first_start:
                if self._bind_owner(telegram_user_id, chat_id):
                    self.logger.info("Bound Telegram owner user_id=%s chat_id=%s", telegram_user_id, chat_id)
                    return True
                # Another update may have won first-bind race; reload and continue checks.
                self._load_owner_binding()
                if self.owner_user_id == telegram_user_id and self.owner_chat_id == chat_id:
                    return True

            await self._reply_unauthorized(update)
            return False

        if telegram_user_id != self.owner_user_id:
            await self._reply_unauthorized(update)
            return False

        if self.owner_chat_id is None:
            # Owner user matched; bind chat on first successful private access.
            self._bind_owner(telegram_user_id, chat_id, persist_user=False)
            return True

        if chat_id != self.owner_chat_id:
            await self._reply_unauthorized(update)
            return False

        return True

    def _bind_owner(self, telegram_user_id: int, chat_id: int, persist_user: bool = True) -> bool:
        """Persist owner binding in DB unless env override is set."""
        self.owner_user_id = telegram_user_id
        self.owner_chat_id = chat_id

        if persist_user and self.config.telegram.owner_user_id is None and self.config.telegram.owner_chat_id is None:
            created = self.database.try_bind_telegram_owner(telegram_user_id, chat_id)
            if not created:
                self._load_owner_binding()
                return False
        return True

    async def _reply_unauthorized(self, update: Update) -> None:
        """Send a friendly unauthorized message with the public repo URL."""
        message = (
            "Hi! This bot is private for my personal coaching setup. "
            f"Please run your own instance: {self.config.telegram.unauthorized_repo_url}"
        )

        # Fail closed for this update so no other handlers run.
        if update.callback_query and update.callback_query.message:
            await update.callback_query.answer()
            await update.callback_query.message.reply_text(message)
        elif update.effective_message:
            await update.effective_message.reply_text(message)

        raise ApplicationHandlerStop()
    
    async def _get_or_create_user(self, telegram_user_id: int, username: str, first_name: str) -> Optional[User]:
        """Get existing user or create a single-owner local account."""
        try:
            with self.database.get_session() as session:
                user = session.query(User).filter(User.telegram_user_id == telegram_user_id).first()
                
                if user:
                    user.last_login = datetime.utcnow()
                    session.commit()
                    self.active_users[telegram_user_id] = str(user.id)
                    self.logger.info(f"User {user.username} logged in")
                    return user

                user = User(
                    id=str(uuid.uuid4()),
                    telegram_user_id=telegram_user_id,
                    username=username or "coach_owner",
                    first_name=first_name,
                    created_at=datetime.utcnow(),
                    last_login=datetime.utcnow()
                )
                session.add(user)
                session.commit()
                
                self.active_users[telegram_user_id] = str(user.id)
                self.logger.info(f"Created new user: {telegram_user_id}")
                return user
                
        except Exception as e:
            self.logger.error(f"Error getting/creating user: {e}")
            return None
    
    async def _get_user_id(self, telegram_user_id: int) -> Optional[str]:
        """Get user ID from telegram user ID."""
        if telegram_user_id in self.active_users:
            return self.active_users[telegram_user_id]
        
        try:
            with self.database.get_session() as session:
                user = session.query(User).filter(User.telegram_user_id == telegram_user_id).first()
                if user:
                    self.active_users[telegram_user_id] = str(user.id)
                    return str(user.id)
                    
        except Exception as e:
            self.logger.error(f"Error getting user ID: {e}")
        
        return None
    
    # Formatting Methods
    
    def _format_daily_summary(self, data: Dict[str, Any]) -> str:
        """Format daily summary data."""
        message = "📊 **Today's Summary**\n\n"
        
        if data.get("steps"):
            message += f"🚶 Steps: {data['steps']:,}\n"
        if data.get("calories_burned"):
            message += f"🔥 Calories: {data['calories_burned']:,.0f}\n"
        if data.get("distance_km"):
            message += f"📏 Distance: {data['distance_km']:.1f} km\n"
        if data.get("active_minutes"):
            message += f"⏱️ Active: {data['active_minutes']} min\n"
        
        if data.get("sleep_duration_hours"):
            message += f"💤 Sleep: {data['sleep_duration_hours']:.1f} hours\n"
        if data.get("resting_heart_rate"):
            message += f"❤️ Resting HR: {data['resting_heart_rate']} bpm\n"
        
        return message
    
    def _format_fitness_stats(self, stats: Dict[str, Any]) -> str:
        """Format fitness statistics."""
        message = "📊 **Fitness Statistics**\n\n"
        
        overall_score = stats.get("overall_score", 0)
        fitness_level = stats.get("fitness_level", "unknown")
        
        message += f"**Overall Score:** {overall_score}/100\n"
        message += f"**Fitness Level:** {fitness_level.title()}\n\n"
        
        components = stats.get("component_scores", {})
        message += "**Component Scores:**\n"
        for component, score in components.items():
            message += f"• {component.title()}: {score}/100\n"
        
        recommendations = stats.get("recommendations", [])
        if recommendations:
            message += "\n**Recommendations:**\n"
            for rec in recommendations:
                message += f"• {rec}\n"
        
        return message
    
    def _format_goals(self, goals: List[Dict[str, Any]]) -> str:
        """Format goals list."""
        message = "🎯 **Your Goals**\n\n"
        
        for goal in goals:
            progress = goal.get("progress_percentage", 0)
            message += f"**{goal['goal_name']}**\n"
            message += f"Progress: {progress:.1f}%\n"
            message += f"Target: {goal['target_value']} {goal['unit']}\n"
            message += f"Current: {goal['current_value']} {goal['unit']}\n\n"
        
        return message
    
    def _format_settings(self, settings: Dict[str, Any]) -> str:
        """Format settings."""
        message = "⚙️ **Your Settings**\n\n"
        
        message += f"**Coaching Style:** {settings.get('coaching_style', 'balanced').title()}\n"
        message += f"**Preferred Metrics:** {', '.join(settings.get('preferred_metrics', []))}\n"
        message += f"**Daily Summary:** {'Enabled' if settings.get('enable_daily_summary', True) else 'Disabled'}\n"
        message += f"**Goal Reminders:** {'Enabled' if settings.get('enable_goal_reminders', True) else 'Disabled'}\n"
        message += f"**Units:** {'Metric' if settings.get('use_metric_units', True) else 'Imperial'}\n"
        
        return message
    
    def _format_trends(self, trends: Dict[str, Any]) -> str:
        """Format trends analysis."""
        message = "📈 **Fitness Trends**\n\n"
        
        overall_trend = trends.get("overall_trend", "stable")
        message += f"**Overall Trend:** {overall_trend.title()}\n\n"
        
        insights = trends.get("insights", [])
        if insights:
            message += "**Key Insights:**\n"
            for insight in insights:
                message += f"• {insight}\n"
        
        return message
    
    # Bot Control Methods
    
    async def start_polling(self):
        """Start the bot with polling."""
        try:
            await self.application.initialize()
            await self.application.start()
            await self.application.updater.start_polling()
            
            self.logger.info("🤖 Telegram bot started with polling")
            
        except Exception as e:
            self.logger.error(f"Error starting bot polling: {e}")
            raise
    
    async def stop(self):
        """Stop the bot."""
        try:
            if self.application:
                await self.application.updater.stop()
                await self.application.stop()
                await self.application.shutdown()
            
            self.logger.info("🛑 Telegram bot stopped")
            
        except Exception as e:
            self.logger.error(f"Error stopping bot: {e}")
    
    def get_bot_stats(self) -> Dict[str, Any]:
        """Get bot statistics."""
        uptime = datetime.now() - self.start_time
        return {
            "uptime_seconds": uptime.total_seconds(),
            "total_messages": self.message_count,
            "active_users": len(self.active_users),
            "avg_messages_per_hour": self.message_count / (uptime.total_seconds() / 3600) if uptime.total_seconds() > 0 else 0
        }


def get_telegram_bot(config: Config = None, database: Database = None, coach_agent: Any = None,
                    data_tools: DataTools = None, db_tools: DatabaseTools = None, 
                    analysis_tools: AnalysisTools = None) -> TelegramBot:
    """Get or create telegram bot instance."""
    if not hasattr(get_telegram_bot, '_instance'):
        if not all([config, database, coach_agent, data_tools, db_tools, analysis_tools]):
            raise ValueError("All parameters are required for first initialization")
        get_telegram_bot._instance = TelegramBot(config, database, coach_agent, data_tools, db_tools, analysis_tools)
    return get_telegram_bot._instance


async def init_telegram_bot(config: Config, database: Database, coach_agent: Any,
                           data_tools: DataTools, db_tools: DatabaseTools, 
                           analysis_tools: AnalysisTools) -> TelegramBot:
    """Initialize and return telegram bot instance."""
    bot = TelegramBot(config, database, coach_agent, data_tools, db_tools, analysis_tools)
    await bot.initialize()
    get_telegram_bot._instance = bot
    return bot 