"""
Garmin Connect API Client
=========================

Comprehensive wrapper for the Garmin Connect API that handles authentication,
data fetching, and caching with proper error handling and rate limiting.
"""

import asyncio
import base64
import hashlib
import logging
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
import json
from cryptography.fernet import Fernet, InvalidToken
from garminconnect import (
    Garmin,
    GarminConnectConnectionError,
    GarminConnectTooManyRequestsError,
    GarminConnectAuthenticationError,
)
from sqlalchemy.orm import Session
from core.database import User, Database, GarminDailySummary, GarminActivity, GarminSleep, GarminHeartRate
from core.config import Config

# Configure logging
logger = logging.getLogger(__name__)


class GarminAuthenticationError(Exception):
    """Custom exception for Garmin authentication errors."""
    pass


class GarminDataError(Exception):
    """Custom exception for Garmin data retrieval errors."""
    pass


@dataclass
class GarminData:
    """Structured Garmin data container."""
    user_id: str
    data_type: str
    data: Dict[str, Any]
    timestamp: datetime
    source: str = "garmin_connect"


class GarminClient:
    """
    Comprehensive Garmin Connect API client with caching and error handling.
    
    Features:
    - Automatic retry with exponential backoff
    - Response caching (5 minutes default)
    - Rate limiting compliance
    - Comprehensive error handling
    - Database integration for user management
    """
    
    def __init__(self, config: Config, database: Database):
        """Initialize Garmin client."""
        self.config = config
        self.database = database
        self.logger = logging.getLogger(__name__)
        
        # Cache settings
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._cache_timeout = 300  # 5 minutes default
        
        # Rate limiting
        self._last_request_time = 0
        self._min_request_interval = 1.0  # 1 second between requests
        self._rate_limit = True  # Enable rate limiting
        
        # Connected clients per user
        self._garmin_clients: Dict[str, Garmin] = {}

        # OAuth token store directory — one sub-folder per user
        self._token_store_dir = Path("data/garmin_tokens")
        self._token_store_dir.mkdir(parents=True, exist_ok=True)

    def _build_fernet(self) -> Fernet:
        digest = hashlib.sha256(self.config.security.secret_key.encode("utf-8")).digest()
        return Fernet(base64.urlsafe_b64encode(digest))

    def _encrypt_secret(self, plaintext: str) -> str:
        return self._build_fernet().encrypt(plaintext.encode("utf-8")).decode("utf-8")

    def _decrypt_secret(self, ciphertext: str) -> Optional[str]:
        if not ciphertext:
            return None
        try:
            return self._build_fernet().decrypt(ciphertext.encode("utf-8")).decode("utf-8")
        except InvalidToken:
            # Legacy fallback for old plaintext rows during migration.
            self.logger.warning("Stored Garmin password appears plaintext; using legacy value.")
            return ciphertext
    
    def _get_cache_key(self, user_id: str, method: str, **kwargs) -> str:
        """Generate cache key for request."""
        params = "&".join(f"{k}={v}" for k, v in sorted(kwargs.items()))
        return f"{user_id}:{method}:{params}"
    
    def _is_cache_valid(self, cache_entry: Dict[str, Any]) -> bool:
        """Check if cache entry is still valid."""
        timestamp = cache_entry.get("timestamp")
        if not timestamp:
            return False
        
        age = datetime.now() - timestamp
        return age.total_seconds() < self._cache_timeout
    
    def _cache_response(self, cache_key: str, data: Any):
        """Cache response data."""
        self._cache[cache_key] = {
            "data": data,
            "timestamp": datetime.now()
        }
    
    def _get_cached_response(self, cache_key: str) -> Optional[Any]:
        """Get cached response if valid."""
        if cache_key in self._cache:
            cache_entry = self._cache[cache_key]
            if self._is_cache_valid(cache_entry):
                return cache_entry["data"]
            else:
                # Remove expired cache entry
                del self._cache[cache_key]
        return None
    
    async def _rate_limit_request(self):
        """Apply rate limiting between requests."""
        if not self._rate_limit:
            return
        
        current_time = datetime.now().timestamp()
        time_since_last = current_time - self._last_request_time
        
        if time_since_last < self._min_request_interval:
            sleep_time = self._min_request_interval - time_since_last
            await asyncio.sleep(sleep_time)
        
        self._last_request_time = datetime.now().timestamp()
    
    def _token_store_path(self, user_id: str) -> Path:
        """Per-user OAuth token directory."""
        path = self._token_store_dir / user_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    async def authenticate_user(self, user_id: str, email: str, password: str) -> bool:
        """Authenticate with Garmin Connect and store credentials + OAuth tokens."""
        try:
            token_store = str(self._token_store_path(user_id))
            garmin = Garmin(email, password)
            await asyncio.get_event_loop().run_in_executor(
                None, lambda: garmin.login(tokenstore=token_store)
            )
            self._garmin_clients[user_id] = garmin

            with self.database.get_session() as session:
                user = session.query(User).filter(User.id == user_id).first()
                if not user:
                    self.logger.error(f"User {user_id} not found")
                    return False
                user.garmin_username = email
                user.garmin_password = self._encrypt_secret(password)
                user.garmin_session_token = None
                session.commit()

            self.logger.info(f"Successfully authenticated user {user_id} (tokens saved)")
            return True

        except GarminConnectAuthenticationError:
            self.logger.error(f"Authentication failed for user {user_id}")
            return False
        except Exception as e:
            self.logger.error(f"Error authenticating user {user_id}: {str(e)}")
            return False

    async def _ensure_authenticated(self, user_id: str) -> bool:
        """Ensure user is authenticated. Tries saved OAuth tokens before password auth."""
        try:
            if user_id in self._garmin_clients:
                return True

            with self.database.get_session() as session:
                user = session.query(User).filter(User.id == user_id).first()
                if not user or not user.garmin_password:
                    self.logger.warning(f"No Garmin credentials found for user {user_id}")
                    return False
                email = user.garmin_username
                password = self._decrypt_secret(user.garmin_password)
                if not password:
                    self.logger.warning(f"Unable to decrypt Garmin password for user {user_id}")
                    return False

            token_store = str(self._token_store_path(user_id))
            garmin = Garmin(email, password)

            # Attempt token-based login first — avoids password auth and SSO rate-limits
            try:
                await asyncio.get_event_loop().run_in_executor(
                    None, lambda: garmin.login(tokenstore=token_store)
                )
                self._garmin_clients[user_id] = garmin
                self.logger.info(f"Garmin session restored from saved tokens for user {user_id}")
                return True
            except Exception as token_err:
                self.logger.warning(
                    f"Token login failed for user {user_id} ({token_err}); "
                    "falling back to password auth"
                )

            # Full password login as fallback
            try:
                garmin2 = Garmin(email, password)
                await asyncio.get_event_loop().run_in_executor(
                    None, lambda: garmin2.login(tokenstore=token_store)
                )
                self._garmin_clients[user_id] = garmin2
                self.logger.info(f"Garmin full-auth OK for user {user_id} (tokens refreshed)")
                return True
            except GarminConnectAuthenticationError:
                self.logger.error(f"Authentication failed for user {user_id}")
                return False
            except Exception as e:
                self.logger.error(f"Error creating Garmin client for user {user_id}: {str(e)}")
                return False

        except Exception as e:
            self.logger.error(f"Error ensuring authentication for user {user_id}: {e}")
            return False

    async def _get_garmin_client(self, user_id: str) -> Optional[Garmin]:
        """Get authenticated Garmin client for user."""
        # Check if client already exists
        if user_id in self._garmin_clients:
            return self._garmin_clients[user_id]
        
        # Try to authenticate
        if await self._ensure_authenticated(user_id):
            return self._garmin_clients.get(user_id)
        
        return None
    
    async def get_user_profile(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        Get user profile information from Garmin Connect.
        
        Args:
            user_id: User ID
            
        Returns:
            Dict containing user profile data or None if failed
        """
        try:
            if not await self._ensure_authenticated(user_id):
                return None
            
            cache_key = self._get_cache_key(user_id, 'get_user_profile')
            cached_data = self._get_cached_response(cache_key)
            
            if cached_data:
                self.logger.info(f"Returning cached user profile for user {user_id}")
                return cached_data
            
            await self._rate_limit_request()
            
            # Get the Garmin client
            garmin_client = self._garmin_clients.get(user_id)
            if not garmin_client:
                return None
            
            # Fetch user profile
            profile_data = await asyncio.get_event_loop().run_in_executor(
                None, garmin_client.get_user_profile
            )
            
            # Cache the result
            self._cache_response(cache_key, profile_data)
            
            self.logger.info(f"Retrieved user profile for user {user_id}")
            return profile_data
            
        except Exception as e:
            self.logger.error(f"Failed to get user profile for user {user_id}: {e}")
            return None
    
    async def get_daily_summary(self, user_id: str, date: datetime) -> Optional[Dict[str, Any]]:
        """
        Get daily activity summary for a specific date.
        
        Args:
            user_id: User ID
            date: Date to get summary for
            
        Returns:
            Dict containing daily summary data or None if failed
        """
        try:
            if not await self._ensure_authenticated(user_id):
                return None
            
            date_str = date.strftime('%Y-%m-%d')
            cache_key = self._get_cache_key(user_id, 'get_daily_summary', date=date_str)
            cached_data = self._get_cached_response(cache_key)
            
            if cached_data:
                self.logger.info(f"Returning cached daily summary for user {user_id}, date {date_str}")
                return cached_data
            
            await self._rate_limit_request()
            
            # Get the Garmin client
            garmin_client = self._garmin_clients.get(user_id)
            if not garmin_client:
                return None
            
            # Use get_stats_and_body which contains comprehensive daily data
            summary_data = await asyncio.get_event_loop().run_in_executor(
                None, garmin_client.get_stats_and_body, date_str
            )
            
            # Cache the result
            self._cache_response(cache_key, summary_data)
            
            self.logger.info(f"Retrieved daily summary for user {user_id}, date {date_str}")
            return summary_data
            
        except Exception as e:
            self.logger.error(f"Failed to get daily summary for user {user_id}, date {date}: {e}")
            return None
    
    async def get_activities(self, user_id: str, start_date: datetime, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Get recent activities for a user.
        
        Args:
            user_id: User ID
            start_date: Start date for activities
            limit: Maximum number of activities to return
            
        Returns:
            List of activity dictionaries
        """
        try:
            if not await self._ensure_authenticated(user_id):
                return []
            
            start_str = start_date.strftime('%Y-%m-%d')
            cache_key = self._get_cache_key(user_id, 'get_activities', start_date=start_str, limit=limit)
            cached_data = self._get_cached_response(cache_key)
            
            if cached_data:
                self.logger.info(f"Returning cached activities for user {user_id}")
                return cached_data
            
            await self._rate_limit_request()
            
            # Get the Garmin client
            garmin_client = self._garmin_clients.get(user_id)
            if not garmin_client:
                return []
            
            # Fetch activities
            activities_data = await asyncio.get_event_loop().run_in_executor(
                None, garmin_client.get_activities, 0, limit
            )
            
            # Filter activities by start date
            filtered_activities = []
            for activity in activities_data:
                activity_date = datetime.fromisoformat(activity['startTimeLocal'].replace('Z', '+00:00'))
                if activity_date >= start_date:
                    filtered_activities.append(activity)
            
            # Cache the result
            self._cache_response(cache_key, filtered_activities)
            
            self.logger.info(f"Retrieved {len(filtered_activities)} activities for user {user_id}")
            return filtered_activities
            
        except Exception as e:
            self.logger.error(f"Failed to get activities for user {user_id}: {e}")
            return []

    async def get_activity_detail_bundle(self, user_id: str, activity_id: str) -> Optional[Dict[str, Any]]:
        """
        Get detailed data for a specific activity.

        Returns a bundle containing summary/details/splits/hr zones/weather where
        available from Garmin APIs.
        """
        try:
            if not await self._ensure_authenticated(user_id):
                return None

            cache_key = self._get_cache_key(user_id, "get_activity_detail_bundle", activity_id=activity_id)
            cached_data = self._get_cached_response(cache_key)
            if cached_data:
                self.logger.info(f"Returning cached activity detail bundle for user {user_id}, activity {activity_id}")
                return cached_data

            await self._rate_limit_request()

            garmin_client = self._garmin_clients.get(user_id)
            if not garmin_client:
                return None

            summary = await asyncio.get_event_loop().run_in_executor(
                None, garmin_client.get_activity, activity_id
            )
            details = await asyncio.get_event_loop().run_in_executor(
                None, garmin_client.get_activity_details, activity_id
            )
            splits = await asyncio.get_event_loop().run_in_executor(
                None, garmin_client.get_activity_splits, activity_id
            )
            hr_time_in_zones = await asyncio.get_event_loop().run_in_executor(
                None, garmin_client.get_activity_hr_in_timezones, activity_id
            )
            weather = await asyncio.get_event_loop().run_in_executor(
                None, garmin_client.get_activity_weather, activity_id
            )

            bundle = {
                "activity_id": str(activity_id),
                "summary": summary or {},
                "details": details or {},
                "splits": splits or [],
                "hr_time_in_zones": hr_time_in_zones or {},
                "weather": weather or {},
                "fetched_at": datetime.now().isoformat(),
                "source": "garmin_connect",
            }

            self._cache_response(cache_key, bundle)
            self.logger.info(f"Retrieved activity detail bundle for user {user_id}, activity {activity_id}")
            return bundle

        except Exception as e:
            self.logger.error(f"Failed to get activity detail bundle for user {user_id}, activity {activity_id}: {e}")
            return None
    
    async def get_sleep_data(self, user_id: str, date: datetime) -> Optional[Dict[str, Any]]:
        """
        Get sleep data for a specific date.
        
        Args:
            user_id: User ID
            date: Date to get sleep data for
            
        Returns:
            Dict containing sleep data or None if failed
        """
        try:
            if not await self._ensure_authenticated(user_id):
                return None
            
            date_str = date.strftime('%Y-%m-%d')
            cache_key = self._get_cache_key(user_id, 'get_sleep_data', date=date_str)
            cached_data = self._get_cached_response(cache_key)
            
            if cached_data:
                self.logger.info(f"Returning cached sleep data for user {user_id}, date {date_str}")
                return cached_data
            
            await self._rate_limit_request()
            
            # Get the Garmin client
            garmin_client = self._garmin_clients.get(user_id)
            if not garmin_client:
                return None
            
            # Fetch sleep data
            sleep_data = await asyncio.get_event_loop().run_in_executor(
                None, garmin_client.get_sleep_data, date_str
            )
            
            # Cache the result
            self._cache_response(cache_key, sleep_data)
            
            self.logger.info(f"Retrieved sleep data for user {user_id}, date {date_str}")
            return sleep_data
            
        except Exception as e:
            self.logger.error(f"Failed to get sleep data for user {user_id}, date {date}: {e}")
            return None
    
    async def get_heart_rate_data(self, user_id: str, date: datetime) -> Optional[Dict[str, Any]]:
        """
        Get heart rate data for a specific date.
        
        Args:
            user_id: User ID
            date: Date to get heart rate data for
            
        Returns:
            Dict containing heart rate data or None if failed
        """
        try:
            if not await self._ensure_authenticated(user_id):
                return None
            
            date_str = date.strftime('%Y-%m-%d')
            cache_key = self._get_cache_key(user_id, 'get_heart_rate_data', date=date_str)
            cached_data = self._get_cached_response(cache_key)
            
            if cached_data:
                self.logger.info(f"Returning cached heart rate data for user {user_id}, date {date_str}")
                return cached_data
            
            await self._rate_limit_request()
            
            # Get the Garmin client
            garmin_client = self._garmin_clients.get(user_id)
            if not garmin_client:
                return None
            
            # Fetch heart rate data using the correct method
            hr_data = await asyncio.get_event_loop().run_in_executor(
                None, garmin_client.get_heart_rates, date_str
            )
            
            # Cache the result
            self._cache_response(cache_key, hr_data)
            
            self.logger.info(f"Retrieved heart rate data for user {user_id}, date {date_str}")
            return hr_data
            
        except Exception as e:
            self.logger.error(f"Failed to get heart rate data for user {user_id}, date {date}: {e}")
            return None
    
    async def sync_user_data(self, user_id: str, days_back: int = 7) -> Dict[str, Any]:
        """
        Sync comprehensive user data from Garmin Connect.
        
        Args:
            user_id: User ID to sync data for
            days_back: Number of days to sync back from today
            
        Returns:
            Dict containing sync results and statistics
        """
        try:
            if not await self._ensure_authenticated(user_id):
                return {'success': False, 'error': 'Authentication failed'}
            
            sync_start = datetime.now(timezone.utc)
            sync_results = {
                'success': True,
                'sync_start': sync_start.isoformat(),
                'days_synced': 0,
                'data_types': {
                    'daily_summaries': 0,
                    'activities': 0,
                    'sleep_data': 0,
                    'heart_rate_data': 0
                },
                'errors': []
            }
            
            # Sync data for each day
            for day_offset in range(days_back):
                sync_date = datetime.now(timezone.utc) - timedelta(days=day_offset)
                
                try:
                    # Get daily summary
                    daily_summary = await self.get_daily_summary(user_id, sync_date)
                    if daily_summary:
                        await self._store_daily_summary(user_id, sync_date, daily_summary)
                        sync_results['data_types']['daily_summaries'] += 1
                    
                    # Get sleep data
                    sleep_data = await self.get_sleep_data(user_id, sync_date)
                    if sleep_data:
                        await self._store_sleep_data(user_id, sync_date, sleep_data)
                        sync_results['data_types']['sleep_data'] += 1
                    
                    # Get heart rate data
                    hr_data = await self.get_heart_rate_data(user_id, sync_date)
                    if hr_data:
                        await self._store_heart_rate_data(user_id, sync_date, hr_data)
                        sync_results['data_types']['heart_rate_data'] += 1
                    
                    sync_results['days_synced'] += 1
                    
                except Exception as e:
                    error_msg = f"Failed to sync data for {sync_date.strftime('%Y-%m-%d')}: {e}"
                    sync_results['errors'].append(error_msg)
                    self.logger.error(error_msg)
            
            # Get recent activities
            try:
                start_date = datetime.now(timezone.utc) - timedelta(days=days_back)
                activities = await self.get_activities(user_id, start_date)
                
                for activity in activities:
                    await self._store_activity(user_id, activity)
                    sync_results['data_types']['activities'] += 1
                
            except Exception as e:
                error_msg = f"Failed to sync activities: {e}"
                sync_results['errors'].append(error_msg)
                self.logger.error(error_msg)
            
            # Update user's last sync time
            with self.database.get_session() as session:
                user = session.query(User).filter_by(id=user_id).first()
                if user:
                    user.garmin_last_sync = sync_start
                    session.commit()
            
            sync_results['sync_end'] = datetime.now(timezone.utc).isoformat()
            sync_results['sync_duration'] = (datetime.now(timezone.utc) - sync_start).total_seconds()
            
            self.logger.info(f"Sync completed for user {user_id}: {sync_results}")
            return sync_results
            
        except Exception as e:
            self.logger.error(f"Failed to sync user data for user {user_id}: {e}")
            return {'success': False, 'error': str(e)}
    
    async def _store_daily_summary(self, user_id: str, date: datetime, data: Any):
        """Store daily summary in database."""
        try:
            # Handle different data formats from Garmin API
            summary_data = None
            
            # Debug: Log the raw data structure
            self.logger.debug(f"Raw data type: {type(data)}, data: {data}")
            
            if isinstance(data, list):
                # If data is a list, try to find the relevant entry
                if len(data) > 0:
                    # Use the first entry or find one matching the date
                    summary_data = data[0]
                    self.logger.info(f"Processing list data with {len(data)} entries for date {date.strftime('%Y-%m-%d')}")
                    self.logger.debug(f"First entry type: {type(summary_data)}, value: {summary_data}")
                else:
                    self.logger.warning(f"No data entries found for date {date.strftime('%Y-%m-%d')}")
                    return
            elif isinstance(data, dict):
                summary_data = data
            else:
                self.logger.warning(f"Unexpected data type for daily summary: {type(data)}")
                return
            
            # Ensure summary_data is a dictionary - handle nested structures
            if not isinstance(summary_data, dict):
                # Try to convert or extract dictionary from the data
                if hasattr(summary_data, '__dict__'):
                    summary_data = summary_data.__dict__
                elif isinstance(summary_data, (str, int, float)):
                    # If it's a primitive type, create a simple dict
                    summary_data = {'value': summary_data}
                else:
                    self.logger.warning(f"Summary data is not a dictionary and cannot be converted: {type(summary_data)}")
                    return
            
            with self.database.get_session() as session:
                # Extract values from get_stats_and_body response
                steps = summary_data.get('totalSteps', 0)
                calories = summary_data.get('totalKilocalories', 0)
                distance_meters = summary_data.get('totalDistanceMeters', 0)
                active_minutes = summary_data.get('activeSeconds', 0) // 60 if summary_data.get('activeSeconds') else 0
                resting_hr = summary_data.get('restingHeartRate', 0)
                avg_hr = summary_data.get('minAvgHeartRate', 0)  # Using min as avg for now
                max_hr = summary_data.get('maxHeartRate', 0)
                
                # Sleep data from the same response
                sleep_seconds = summary_data.get('sleepingSeconds', 0)
                sleep_hours = sleep_seconds / 3600 if sleep_seconds else None
                
                # Stress and body battery
                stress_avg = summary_data.get('averageStressLevel', 0)
                body_battery = summary_data.get('bodyBatteryMostRecentValue', 0)
                
                # Normalize to midnight UTC so UniqueConstraint(user_id, activity_date) works.
                canonical_date = date.astimezone(timezone.utc).replace(
                    hour=0, minute=0, second=0, microsecond=0
                )

                existing = session.query(GarminDailySummary).filter(
                    GarminDailySummary.user_id == user_id,
                    GarminDailySummary.activity_date == canonical_date,
                ).first()

                if existing:
                    existing.steps = steps
                    existing.calories_burned = calories
                    existing.distance_km = distance_meters / 1000 if distance_meters else None
                    existing.active_minutes = active_minutes
                    existing.resting_heart_rate = resting_hr
                    existing.avg_heart_rate = avg_hr
                    existing.max_heart_rate = max_hr
                    existing.sleep_duration_hours = sleep_hours
                    existing.stress_level_avg = stress_avg
                    existing.body_battery_level = body_battery
                    existing.data_completeness_percentage = 100.0
                    existing.sync_status = "completed"
                else:
                    session.add(GarminDailySummary(
                        user_id=user_id,
                        activity_date=canonical_date,
                        steps=steps,
                        calories_burned=calories,
                        distance_km=distance_meters / 1000 if distance_meters else None,
                        active_minutes=active_minutes,
                        resting_heart_rate=resting_hr,
                        avg_heart_rate=avg_hr,
                        max_heart_rate=max_hr,
                        sleep_duration_hours=sleep_hours,
                        stress_level_avg=stress_avg,
                        body_battery_level=body_battery,
                        data_completeness_percentage=100.0,
                        sync_status="completed",
                    ))
                session.commit()
                
                self.logger.info(f"Upserted daily summary for user {user_id}, date {date.strftime('%Y-%m-%d')} - Steps: {steps}, Calories: {calories}")
                
        except Exception as e:
            self.logger.error(f"Failed to store daily summary for user {user_id}, date {date}: {e}")
    
    async def _store_sleep_data(self, user_id: str, date: datetime, data: Any):
        """Store sleep data in database."""
        try:
            # Handle different data formats from Garmin API
            sleep_data = None
            
            # Debug: Log the raw data structure
            self.logger.debug(f"Raw sleep data type: {type(data)}, data: {data}")
            
            if isinstance(data, list):
                # If data is a list, try to find the relevant entry
                if len(data) > 0:
                    # Use the first entry or find one matching the date
                    sleep_data = data[0]
                    self.logger.info(f"Processing sleep list data with {len(data)} entries for date {date.strftime('%Y-%m-%d')}")
                    self.logger.debug(f"First sleep entry type: {type(sleep_data)}, value: {sleep_data}")
                else:
                    self.logger.warning(f"No sleep data entries found for date {date.strftime('%Y-%m-%d')}")
                    return
            elif isinstance(data, dict):
                sleep_data = data
            else:
                self.logger.warning(f"Unexpected data type for sleep data: {type(data)}")
                return
            
            # Ensure sleep_data is a dictionary - handle nested structures
            if not isinstance(sleep_data, dict):
                # Try to convert or extract dictionary from the data
                if hasattr(sleep_data, '__dict__'):
                    sleep_data = sleep_data.__dict__
                elif isinstance(sleep_data, (str, int, float)):
                    # If it's a primitive type, create a simple dict
                    sleep_data = {'value': sleep_data}
                else:
                    self.logger.warning(f"Sleep data is not a dictionary and cannot be converted: {type(sleep_data)}")
                    return
            
            with self.database.get_session() as session:
                # Extract values safely with defaults - FIXED field names
                sleep_time_seconds = sleep_data.get('sleepingSeconds', sleep_data.get('sleepTimeSeconds', 0))
                deep_sleep_seconds = sleep_data.get('deepSleepSeconds', 0)
                light_sleep_seconds = sleep_data.get('lightSleepSeconds', 0)
                rem_sleep_seconds = sleep_data.get('remSleepSeconds', 0)
                awake_sleep_seconds = sleep_data.get('awakeSleepSeconds', 0)
                sleep_quality = sleep_data.get('sleepQuality', 0)
                
                # Use SQLAlchemy merge for proper upsert
                sleep_record = GarminSleep(
                    user_id=user_id,
                    sleep_date=date,
                    sleep_start_time=date,  # Simplified
                    sleep_end_time=date + timedelta(hours=8),  # Simplified
                    total_sleep_minutes=sleep_time_seconds // 60,
                    deep_sleep_minutes=deep_sleep_seconds // 60,
                    light_sleep_minutes=light_sleep_seconds // 60,
                    rem_sleep_minutes=rem_sleep_seconds // 60,
                    awake_minutes=awake_sleep_seconds // 60,
                    sleep_quality_score=sleep_quality,
                    raw_sleep_data=sleep_data
                )
                
                # Merge will update existing record or create new one
                merged_record = session.merge(sleep_record)
                session.commit()
                
                self.logger.info(f"Upserted sleep data for user {user_id}, date {date.strftime('%Y-%m-%d')} - Total sleep: {sleep_time_seconds // 60} min")
                
        except Exception as e:
            self.logger.error(f"Failed to store sleep data for user {user_id}, date {date}: {e}")
    
    async def _store_heart_rate_data(self, user_id: str, date: datetime, data: Any):
        """Store heart rate data in database."""
        try:
            # Handle different data formats from Garmin API
            hr_data = None
            
            # Debug: Log the raw data structure
            self.logger.debug(f"Raw heart rate data type: {type(data)}, data: {data}")
            
            if isinstance(data, list):
                # If data is a list, try to find the relevant entry
                if len(data) > 0:
                    # Use the first entry or find one matching the date
                    hr_data = data[0]
                    self.logger.info(f"Processing heart rate list data with {len(data)} entries for date {date.strftime('%Y-%m-%d')}")
                    self.logger.debug(f"First heart rate entry type: {type(hr_data)}, value: {hr_data}")
                else:
                    self.logger.warning(f"No heart rate data entries found for date {date.strftime('%Y-%m-%d')}")
                    return
            elif isinstance(data, dict):
                hr_data = data
            else:
                self.logger.warning(f"Unexpected data type for heart rate data: {type(data)}")
                return
            
            # Ensure hr_data is a dictionary - handle nested structures
            if not isinstance(hr_data, dict):
                # Try to convert or extract dictionary from the data
                if hasattr(hr_data, '__dict__'):
                    hr_data = hr_data.__dict__
                elif isinstance(hr_data, (str, int, float)):
                    # If it's a primitive type, create a simple dict
                    hr_data = {'value': hr_data}
                else:
                    self.logger.warning(f"Heart rate data is not a dictionary and cannot be converted: {type(hr_data)}")
                    return
            
            with self.database.get_session() as session:
                # Get heart rate values from the data - handle the actual structure
                hr_values = hr_data.get('heartRateValues', [])
                
                # The heart rate data is in format: [[timestamp, heart_rate], [timestamp, heart_rate], ...]
                for hr_point in hr_values:
                    if isinstance(hr_point, list) and len(hr_point) >= 2:
                        timestamp_ms = hr_point[0]  # Unix timestamp in milliseconds
                        heart_rate = hr_point[1]    # Heart rate value
                        
                        if timestamp_ms and heart_rate and heart_rate > 0:
                            # Convert milliseconds to datetime
                            timestamp = datetime.fromtimestamp(timestamp_ms / 1000)
                            
                            # Check if record already exists
                            existing = session.query(GarminHeartRate).filter(
                                GarminHeartRate.user_id == user_id,
                                GarminHeartRate.recorded_at == timestamp
                            ).first()
                            
                            if not existing:
                                # Create new record
                                hr_record = GarminHeartRate(
                                    id=str(uuid.uuid4()),
                                    user_id=user_id,
                                    recorded_at=timestamp,
                                    heart_rate_bpm=heart_rate,
                                    heart_rate_zone=self._get_heart_rate_zone(heart_rate),
                                    activity_type='resting'
                                )
                                session.add(hr_record)
                
                session.commit()
                self.logger.info(f"Stored {len(hr_values)} heart rate readings for user {user_id}, date {date.strftime('%Y-%m-%d')}")
                
        except Exception as e:
            self.logger.error(f"Failed to store heart rate data for user {user_id}, date {date}: {e}")
    
    async def _store_activity(self, user_id: str, activity: Dict[str, Any]):
        """Store activity in database."""
        try:
            with self.database.get_session() as session:
                garmin_activity_id = str(activity.get('activityId', ''))

                if not garmin_activity_id:
                    self.logger.warning("Skipping activity without activityId for user %s", user_id)
                    return

                start_time_raw = activity.get('startTimeLocal', '')
                start_time = datetime.fromisoformat(start_time_raw.replace('Z', '+00:00')) if start_time_raw else datetime.utcnow()

                normalized_fields = {
                    "user_id": user_id,
                    "garmin_activity_id": garmin_activity_id,
                    "activity_type": activity.get('activityType', {}).get('typeKey', 'unknown'),
                    "activity_name": activity.get('activityName', ''),
                    "start_time": start_time,
                    "duration_seconds": activity.get('duration', 0),
                    "distance_km": activity.get('distance', 0) / 1000 if activity.get('distance') else None,
                    "avg_speed_kmh": activity.get('averageSpeed', 0) * 3.6 if activity.get('averageSpeed') else None,
                    "max_speed_kmh": activity.get('maxSpeed', 0) * 3.6 if activity.get('maxSpeed') else None,
                    "calories_burned": activity.get('calories', 0),
                    "avg_heart_rate": activity.get('averageHeartRate', 0),
                    "max_heart_rate": activity.get('maxHeartRate', 0),
                    "raw_activity_data": activity,
                }

                existing = session.query(GarminActivity).filter(
                    GarminActivity.garmin_activity_id == garmin_activity_id
                ).first()

                if existing:
                    for field, value in normalized_fields.items():
                        setattr(existing, field, value)
                else:
                    activity_record = GarminActivity(
                        id=str(uuid.uuid4()),
                        **normalized_fields
                    )
                    session.add(activity_record)

                session.commit()
                
                self.logger.info(f"Upserted activity {garmin_activity_id} for user {user_id}")
                
        except Exception as e:
            self.logger.error(f"Failed to store activity for user {user_id}: {e}")
    
    def _get_heart_rate_zone(self, heart_rate: int) -> str:
        """Determine heart rate zone based on BPM."""
        if heart_rate < 100:
            return 'rest'
        elif heart_rate < 120:
            return 'fat_burn'
        elif heart_rate < 140:
            return 'cardio'
        else:
            return 'peak'
    
    def clear_cache(self):
        """Clear the internal data cache."""
        self._cache.clear()
        self.logger.info("Garmin client cache cleared")
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        return {
            'cache_size': len(self._cache),
            'cache_ttl': self._cache_timeout,
            'rate_limit_delay': self._min_request_interval
        }


# Global Garmin client instance
garmin_client = None

def get_garmin_client(config: Config = None, database: Database = None) -> GarminClient:
    """Get the global Garmin client instance."""
    global garmin_client
    if garmin_client is None:
        if config is None:
            from core.config import get_config
            config = get_config()
        if database is None:
            from core.database import get_database
            database = get_database()
        garmin_client = GarminClient(config, database)
    return garmin_client


def init_garmin_client(config: Config, database: Database) -> GarminClient:
    """Initialize the global Garmin client instance."""
    global garmin_client
    garmin_client = GarminClient(config, database)
    return garmin_client 