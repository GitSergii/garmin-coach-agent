#!/usr/bin/env python3
"""
Real Garmin Data Sync Script
============================

This script authenticates with Garmin Connect and syncs real data.
It is intended for production-grade personal data synchronization.
"""

import sys
import os
import asyncio
from datetime import datetime, timedelta, timezone
import logging
from sqlalchemy import text

# Add src to path
sys.path.insert(0, 'src')

from core.config import init_config
from core.database import (
    init_database,
    User,
    GarminDailySummary,
    GarminActivity,
    GarminSleep,
    GarminHeartRate,
)
from core.garmin_client import init_garmin_client
from tools.db_tools import init_database_tools

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def _resolve_target_user(session):
    """Resolve target user for sync in a self-hosted single-user deployment."""
    owner_binding = None
    try:
        owner_binding = session.execute(
            text("SELECT value FROM app_settings WHERE key = 'telegram_owner_binding' LIMIT 1")
        ).scalar()
    except Exception:
        owner_binding = None

    if owner_binding:
        try:
            owner_user_id, _owner_chat_id = owner_binding.split(":", 1)
            owner_telegram_id = int(owner_user_id)
            user = session.query(User).filter(User.telegram_user_id == owner_telegram_id).first()
            if user:
                return user
        except Exception:
            pass

    user = session.query(User).filter(User.garmin_username.isnot(None)).order_by(User.created_at.asc()).first()
    return user

async def sync_real_garmin_data():
    """Sync real Garmin data for the personal user."""
    print("🚀 Starting REAL Garmin data sync...")
    print("=" * 50)
    
    try:
        # Initialize components
        config = init_config()
        database = init_database(config)
        garmin_client = init_garmin_client(config, database)
        db_tools = init_database_tools(database, config)
        
        # Resolve the self-hosted owner user
        with database.get_session() as session:
            user = _resolve_target_user(session)
            if not user:
                print("❌ No Garmin-configured user found. Use /setup in Telegram first.")
                return False
            
            user_id = str(user.id)
            garmin_email = user.garmin_username
            
            print(f"✅ Found user: {user.username} (ID: {user_id})")
            print(f"📧 Garmin email: {garmin_email}")
            
            # Ensure Garmin authentication using stored encrypted credentials.
            print("\n🔐 Verifying Garmin authentication...")
            auth_success = await garmin_client._ensure_authenticated(user_id)
            if not auth_success:
                print("❌ Garmin authentication failed (stored credentials invalid).")
                print("Please run /setup in Telegram and save Garmin credentials again.")
                return False
            
            print("✅ Garmin authentication successful!")
            
            # Sync data for the last 7 days
            # end_date = datetime.now()
            # start_date = end_date - timedelta(days=7)

            # --- FIX: Sync all available data for the last 365 days (or adjust as needed) ---
            end_date = datetime.now()
            start_date = end_date - timedelta(days=365)  # Change 365 to a larger number if you want more

            print(f"\n📊 Syncing data from {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
            
            # Sync daily summaries
            print("\n📈 Syncing daily summaries...")
            daily_sync_count = 0
            current_date = start_date
            while current_date <= end_date:
                try:
                    daily_data = await garmin_client.get_daily_summary(user_id, current_date)
                    if daily_data:
                        await garmin_client._store_daily_summary(user_id, current_date, daily_data)
                        daily_sync_count += 1
                        print(f"   ✅ {current_date.strftime('%Y-%m-%d')}: {daily_data.get('steps', 0)} steps")
                    else:
                        print(f"   ⚠️  {current_date.strftime('%Y-%m-%d')}: No data available")
                except Exception as e:
                    print(f"   ❌ {current_date.strftime('%Y-%m-%d')}: Error - {e}")
                
                current_date += timedelta(days=1)
            
            # Sync activities
            print("\n🏃 Syncing activities...")
            try:
                activities = await garmin_client.get_activities(user_id, start_date, limit=500)
                activity_sync_count = 0
                for activity in activities:
                    try:
                        await garmin_client._store_activity(user_id, activity)
                        activity_sync_count += 1
                        activity_type = activity.get('activityType', {}).get('typeKey', 'unknown')
                        distance = activity.get('distance', 0)
                        print(f"   ✅ {activity_type}: {distance:.2f} km")
                    except Exception as e:
                        print(f"   ❌ Activity sync error: {e}")
                
                print(f"   ✅ Activities synced: {activity_sync_count}")
            except Exception as e:
                print(f"   ❌ Activities sync error: {e}")
            
            # Sync sleep data (detailed breakdown: deep, REM, quality)
            print("\n💤 Syncing sleep data...")
            sleep_sync_count = 0
            current_date = start_date
            while current_date <= end_date:
                try:
                    sleep_data = await garmin_client.get_sleep_data(user_id, current_date)
                    if sleep_data:
                        await garmin_client._store_sleep_data(user_id, current_date, sleep_data)
                        sleep_sync_count += 1
                        dto = sleep_data.get("dailySleepDTO", {}) if isinstance(sleep_data, dict) else {}
                        total_min = (dto.get("sleepTimeSeconds") or 0) // 60
                        print(f"   ✅ {current_date.strftime('%Y-%m-%d')}: {total_min} min sleep")
                    else:
                        print(f"   ⚠️  {current_date.strftime('%Y-%m-%d')}: No sleep data")
                except Exception as e:
                    print(f"   ❌ {current_date.strftime('%Y-%m-%d')}: Sleep sync error - {e}")
                current_date += timedelta(days=1)
            
            # Sync heart rate data (last 3 days for detailed data)
            print("\n❤️ Syncing heart rate data...")
            hr_sync_count = 0
            hr_start_date = end_date - timedelta(days=3)
            current_date = hr_start_date
            while current_date <= end_date:
                try:
                    hr_data = await garmin_client.get_heart_rate_data(user_id, current_date)
                    if hr_data:
                        await garmin_client._store_heart_rate_data(user_id, current_date, hr_data)
                        hr_sync_count += 1
                        readings = len(hr_data.get('heartRateValues', []))
                        print(f"   ✅ {current_date.strftime('%Y-%m-%d')}: {readings} readings")
                    else:
                        print(f"   ⚠️  {current_date.strftime('%Y-%m-%d')}: No HR data")
                except Exception as e:
                    print(f"   ❌ {current_date.strftime('%Y-%m-%d')}: HR sync error - {e}")
                
                current_date += timedelta(days=1)
            
            # Update user's last sync time
            user.last_garmin_sync_at = datetime.now(timezone.utc)
            session.commit()
            
            # Show summary
            print("\n" + "=" * 50)
            print("📊 SYNC SUMMARY")
            print("=" * 50)
            print(f"✅ Daily summaries synced: {daily_sync_count}")
            print(f"✅ Activities synced: {activity_sync_count}")
            print(f"✅ Sleep records synced: {sleep_sync_count}")
            print(f"✅ Heart rate days synced: {hr_sync_count}")
            print(f"✅ Last sync: {user.last_garmin_sync_at}")
            
            # Show data summary
            await show_real_data_summary(database, user_id)
            
            return True
            
    except Exception as e:
        print(f"❌ Error during Garmin sync: {e}")
        import traceback
        traceback.print_exc()
        return False

async def show_real_data_summary(database, user_id: str):
    """Show summary of real synced data."""
    with database.get_session() as session:
        daily_count = session.query(GarminDailySummary).filter(GarminDailySummary.user_id == user_id).count()
        activity_count = session.query(GarminActivity).filter(GarminActivity.user_id == user_id).count()
        sleep_count = session.query(GarminSleep).filter(GarminSleep.user_id == user_id).count()
        hr_count = session.query(GarminHeartRate).filter(GarminHeartRate.user_id == user_id).count()
        
        print(f"\n📊 REAL DATA SUMMARY:")
        print(f"   Daily Summaries: {daily_count}")
        print(f"   Activities: {activity_count}")
        print(f"   Sleep Records: {sleep_count}")
        print(f"   Heart Rate Readings: {hr_count}")
        print(f"   Total Data Points: {daily_count + activity_count + sleep_count + hr_count}")
        
        if daily_count > 0:
            # Show latest daily summary
            latest_summary = session.query(GarminDailySummary).filter(
                GarminDailySummary.user_id == user_id
            ).order_by(GarminDailySummary.activity_date.desc()).first()
            
            if latest_summary:
                print(f"\n📈 Latest Summary ({latest_summary.activity_date.strftime('%Y-%m-%d')}):")
                print(f"   Steps: {latest_summary.steps:,}" if latest_summary.steps else "   Steps: N/A")
                print(f"   Calories: {latest_summary.calories_burned:,.0f}" if latest_summary.calories_burned else "   Calories: N/A")
                print(f"   Sleep: {latest_summary.sleep_duration_hours:.1f}h" if latest_summary.sleep_duration_hours else "   Sleep: N/A")
                print(f"   Resting HR: {latest_summary.resting_heart_rate} bpm" if latest_summary.resting_heart_rate else "   Resting HR: N/A")

async def test_garmin_connection():
    """Test Garmin connection without syncing data."""
    print("🔍 Testing Garmin connection...")
    
    try:
        config = init_config()
        database = init_database(config)
        garmin_client = init_garmin_client(config, database)
        
        # Resolve the self-hosted owner user
        with database.get_session() as session:
            user = _resolve_target_user(session)
            if not user:
                print("❌ No Garmin-configured user found")
                return False
            
            user_id = str(user.id)
            garmin_email = user.garmin_username
            
            print(f"📧 Testing with: {garmin_email}")
            
            # Test authentication using stored encrypted credentials
            auth_success = await garmin_client._ensure_authenticated(user_id)
            
            if auth_success:
                print("✅ Garmin authentication successful!")
                
                # Test getting user profile
                try:
                    profile = await garmin_client.get_user_profile(user_id)
                    if profile:
                        print(f"✅ User profile retrieved: {profile.get('displayName', 'Unknown')}")
                    else:
                        print("⚠️  Could not retrieve user profile")
                except Exception as e:
                    print(f"⚠️  Profile retrieval error: {e}")
                
                return True
            else:
                print("❌ Garmin authentication failed!")
                return False
                
    except Exception as e:
        print(f"❌ Connection test error: {e}")
        return False

async def main():
    """Main function."""
    print("🎯 REAL Garmin Data Sync")
    print("=" * 50)
    
    # Check command line arguments
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        success = await test_garmin_connection()
    else:
        success = await sync_real_garmin_data()
    
    if success:
        print("\n🎉 Real Garmin sync completed successfully!")
        print("🤖 Your bot now has REAL data to work with!")
        print("\nNext steps:")
        print("1. Start the bot: python run.py")
        print("2. Send /start to your bot")
        print("3. Ask questions like 'How did I do today?'")
    else:
        print("\n❌ Real Garmin sync failed!")
        return False
    
    return True

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1) 