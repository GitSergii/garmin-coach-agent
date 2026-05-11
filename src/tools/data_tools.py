"""
Data Tools for AI Coach Agent
=============================

This module provides data fetching and processing tools for the AI coaching agent.
Handles integration with Garmin data and provides processed insights.
"""

import logging
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
import pandas as pd
import numpy as np
from statistics import mean, median, stdev

from core.config import Config
from core.garmin_client import GarminClient
from tools.db_tools import DatabaseTools


logger = logging.getLogger(__name__)


class DataTools:
    """
    Data fetching and processing tools for the AI coaching agent.
    
    Provides:
    - Garmin data fetching and synchronization
    - Data processing and aggregation
    - Trend analysis and pattern recognition
    - Performance metrics calculation
    - Data quality assessment
    """
    
    def __init__(self, garmin_client: GarminClient, db_tools: DatabaseTools, config: Config):
        """Initialize data tools."""
        self.garmin_client = garmin_client
        self.db_tools = db_tools
        self.config = config
        self.logger = logging.getLogger(__name__)

    @staticmethod
    def _normalize_activity_timestamp(activity: Dict[str, Any]) -> datetime:
        """Resolve activity timestamp from normalized or Garmin raw fields."""
        start_time = activity.get("start_time")
        if isinstance(start_time, datetime):
            return start_time
        if isinstance(start_time, str) and start_time:
            try:
                return datetime.fromisoformat(start_time.replace("Z", "+00:00"))
            except ValueError:
                pass
        raw_start = activity.get("startTimeLocal")
        if isinstance(raw_start, str) and raw_start:
            try:
                return datetime.fromisoformat(raw_start.replace("Z", "+00:00"))
            except ValueError:
                pass
        return datetime.min
    
    # Data Fetching Tools
    
    async def fetch_user_data(self, user_id: str) -> Dict[str, Any]:
        """Fetch comprehensive user data from database."""
        try:
            profile = await self.db_tools.get_user_profile(user_id)
            if not profile:
                return {}
            
            # Get recent fitness data
            end_date = datetime.now()
            start_date = end_date - timedelta(days=30)
            
            daily_summaries = await self.db_tools.get_daily_summaries(user_id, start_date, end_date)
            recent_activities = await self.db_tools.get_recent_activities(user_id, 10)
            
            return {
                "profile": profile,
                "daily_summaries": daily_summaries,
                "recent_activities": recent_activities,
                "data_range": {
                    "start_date": start_date,
                    "end_date": end_date,
                    "days": 30
                }
            }
            
        except Exception as e:
            self.logger.error(f"Error fetching user data for {user_id}: {e}")
            return {}
    
    async def fetch_daily_summary(self, user_id: str, date: datetime) -> Dict[str, Any]:
        """Fetch daily summary for a specific date."""
        try:
            # Try to get from database first
            summaries = await self.db_tools.get_daily_summaries(user_id, date, date)
            if summaries:
                return summaries[0]
            
            # Fetch from Garmin if not in database
            garmin_data = await self.garmin_client.get_daily_summary(user_id, date)
            if garmin_data:
                # Store in database
                await self.db_tools.store_daily_summary(user_id, date, garmin_data)
                return garmin_data
            
            return {}
            
        except Exception as e:
            self.logger.error(f"Error fetching daily summary for {user_id} on {date}: {e}")
            return {}
    
    async def fetch_activity_data(self, user_id: str, days_back: int = 7) -> List[Dict[str, Any]]:
        """Fetch recent activity data."""
        try:
            # Get from database first
            activities = await self.db_tools.get_recent_activities(user_id, days_back * 2)  # Get more to ensure we have enough
            
            # Filter to requested time range
            cutoff_date = datetime.now() - timedelta(days=days_back)
            recent_activities = [
                activity for activity in activities
                if self._normalize_activity_timestamp(activity) >= cutoff_date
            ]
            
            # If we don't have enough recent data, fetch from Garmin
            if len(recent_activities) < 5:  # Threshold for sufficient data
                start_date = datetime.now() - timedelta(days=days_back)
                garmin_activities = await self.garmin_client.get_activities(user_id, start_date)
                
                # Store new activities in database
                for activity in garmin_activities:
                    await self.db_tools.store_activity(user_id, activity)
                
                # Combine and deduplicate
                all_activities = recent_activities + garmin_activities
                # Simple deduplication by start time
                seen_times = set()
                recent_activities = []
                for activity in all_activities:
                    start_time = self._normalize_activity_timestamp(activity)
                    if start_time not in seen_times:
                        seen_times.add(start_time)
                        recent_activities.append(activity)
            
            return recent_activities
            
        except Exception as e:
            self.logger.error(f"Error fetching activity data for {user_id}: {e}")
            return []

    async def fetch_activity_details(self, user_id: str, garmin_activity_id: str) -> Dict[str, Any]:
        """Fetch full details for one activity by Garmin activity ID."""
        try:
            existing = await self.db_tools.get_activity_by_garmin_id(user_id, garmin_activity_id)
            detail_bundle = await self.garmin_client.get_activity_detail_bundle(user_id, garmin_activity_id)
            if not detail_bundle:
                # Fall back to database-only payload when Garmin detail endpoints are unavailable.
                if existing:
                    return {
                        "activity_id": garmin_activity_id,
                        "activity": existing,
                        "details": {},
                        "splits": [],
                        "hr_time_in_zones": {},
                        "weather": {},
                        "source": "database",
                    }
                return {}

            summary = detail_bundle.get("summary") or {}
            if summary:
                await self.db_tools.store_activity(user_id, summary)
            elif existing:
                summary = existing

            return {
                "activity_id": garmin_activity_id,
                "activity": summary,
                "details": detail_bundle.get("details", {}),
                "splits": detail_bundle.get("splits", []),
                "hr_time_in_zones": detail_bundle.get("hr_time_in_zones", {}),
                "weather": detail_bundle.get("weather", {}),
                "source": "garmin_connect",
            }
        except Exception as e:
            self.logger.error(f"Error fetching activity details for {user_id}, activity {garmin_activity_id}: {e}")
            return {}

    async def fetch_latest_running_activity_details(self, user_id: str, days_back: int = 30) -> Dict[str, Any]:
        """Fetch full details for most recent running activity."""
        try:
            activities = await self.fetch_activity_data(user_id, days_back)
            running = [
                activity for activity in activities
                if "run" in str(activity.get("activity_type", "")).lower()
            ]
            if not running:
                return {}

            running.sort(key=self._normalize_activity_timestamp, reverse=True)
            latest = running[0]

            activity_id = latest.get("garmin_activity_id")
            if not activity_id:
                raw = latest.get("raw_activity_data") or {}
                activity_id = raw.get("activityId")
            if not activity_id:
                return {}

            return await self.fetch_activity_details(user_id, str(activity_id))
        except Exception as e:
            self.logger.error(f"Error fetching latest running activity details for {user_id}: {e}")
            return {}
    
    async def fetch_sleep_data(self, user_id: str, date: datetime) -> Dict[str, Any]:
        """Fetch sleep data for a specific date."""
        try:
            # Try Garmin first for sleep data (usually more complete)
            garmin_data = await self.garmin_client.get_sleep_data(user_id, date)
            if garmin_data:
                await self.db_tools.store_sleep_data(user_id, date, garmin_data)
                return garmin_data
            
            # Fallback to database
            summaries = await self.db_tools.get_daily_summaries(user_id, date, date)
            if summaries:
                summary = summaries[0]
                return {
                    "sleep_duration_hours": summary.get("sleep_duration_hours"),
                    "sleep_quality_score": summary.get("sleep_quality_score"),
                    "deep_sleep_minutes": summary.get("deep_sleep_minutes"),
                    "rem_sleep_minutes": summary.get("rem_sleep_minutes"),
                    "date": date
                }
            
            return {}
            
        except Exception as e:
            self.logger.error(f"Error fetching sleep data for {user_id} on {date}: {e}")
            return {}
    
    async def fetch_heart_rate_data(self, user_id: str, date: datetime) -> Dict[str, Any]:
        """Fetch heart rate data for a specific date."""
        try:
            # Try Garmin first for detailed HR data
            garmin_data = await self.garmin_client.get_heart_rate_data(user_id, date)
            if garmin_data:
                await self.db_tools.store_heart_rate_data(user_id, date, garmin_data)
                return garmin_data
            
            # Fallback to summary data
            summaries = await self.db_tools.get_daily_summaries(user_id, date, date)
            if summaries:
                summary = summaries[0]
                return {
                    "resting_heart_rate": summary.get("resting_heart_rate"),
                    "avg_heart_rate": summary.get("avg_heart_rate"),
                    "max_heart_rate": summary.get("max_heart_rate"),
                    "date": date
                }
            
            return {}
            
        except Exception as e:
            self.logger.error(f"Error fetching heart rate data for {user_id} on {date}: {e}")
            return {}
    
    # Data Processing Tools
    
    async def process_daily_trends(self, user_id: str, metric: str, days_back: int = 30) -> Dict[str, Any]:
        """Process daily trends for a specific metric."""
        try:
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days_back)
            
            summaries = await self.db_tools.get_daily_summaries(user_id, start_date, end_date)
            
            if not summaries:
                return {"error": "No data available for trend analysis"}
            
            # Extract metric values
            values = []
            dates = []
            for summary in summaries:
                value = summary.get(metric)
                if value is not None:
                    values.append(value)
                    dates.append(summary.get("date"))
            
            if not values:
                return {"error": f"No {metric} data available"}
            
            # Calculate trend statistics
            trend_stats = self._calculate_trend_stats(values, dates)
            
            return {
                "metric": metric,
                "period_days": days_back,
                "data_points": len(values),
                "current_value": values[-1] if values else None,
                "trend_direction": trend_stats["trend_direction"],
                "trend_strength": trend_stats["trend_strength"],
                "average": trend_stats["average"],
                "median": trend_stats["median"],
                "std_deviation": trend_stats["std_deviation"],
                "min_value": trend_stats["min_value"],
                "max_value": trend_stats["max_value"],
                "improvement_percentage": trend_stats["improvement_percentage"],
                "consistency_score": trend_stats["consistency_score"],
                "weekly_averages": trend_stats["weekly_averages"]
            }
            
        except Exception as e:
            self.logger.error(f"Error processing daily trends for {user_id}: {e}")
            return {"error": str(e)}
    
    def _calculate_trend_stats(self, values: List[float], dates: List[datetime]) -> Dict[str, Any]:
        """Calculate comprehensive trend statistics."""
        if not values:
            return {}
        
        # Basic statistics
        avg = mean(values)
        med = median(values)
        std_dev = stdev(values) if len(values) > 1 else 0
        min_val = min(values)
        max_val = max(values)
        
        # Trend direction (simple linear trend)
        if len(values) >= 2:
            # Calculate slope using first and last values
            first_val = values[0]
            last_val = values[-1]
            change = last_val - first_val
            improvement_pct = (change / first_val) * 100 if first_val != 0 else 0
            
            if abs(change) < (std_dev * 0.5):  # Within half standard deviation
                trend_direction = "stable"
                trend_strength = "weak"
            elif change > 0:
                trend_direction = "increasing"
                trend_strength = "strong" if abs(improvement_pct) > 10 else "moderate"
            else:
                trend_direction = "decreasing"
                trend_strength = "strong" if abs(improvement_pct) > 10 else "moderate"
        else:
            trend_direction = "unknown"
            trend_strength = "unknown"
            improvement_pct = 0
        
        # Consistency score (lower std deviation relative to mean = higher consistency)
        consistency_score = max(0, min(100, 100 - (std_dev / avg * 100))) if avg != 0 else 0
        
        # Weekly averages
        weekly_averages = []
        if len(values) >= 7:
            for i in range(0, len(values), 7):
                week_values = values[i:i+7]
                weekly_averages.append(mean(week_values))
        
        return {
            "average": avg,
            "median": med,
            "std_deviation": std_dev,
            "min_value": min_val,
            "max_value": max_val,
            "trend_direction": trend_direction,
            "trend_strength": trend_strength,
            "improvement_percentage": improvement_pct,
            "consistency_score": consistency_score,
            "weekly_averages": weekly_averages
        }
    
    async def analyze_activity_patterns(self, user_id: str, days_back: int = 30) -> Dict[str, Any]:
        """Analyze activity patterns and workout frequency."""
        try:
            activities = await self.fetch_activity_data(user_id, days_back)
            
            if not activities:
                return {"error": "No activity data available"}
            
            # Group activities by type
            activity_types = {}
            total_duration = 0
            total_distance = 0
            total_calories = 0
            
            for activity in activities:
                activity_type = activity.get("activity_type", "unknown")
                duration = activity.get("duration_seconds", 0)
                distance = activity.get("distance_km", 0) or 0
                calories = activity.get("calories_burned", 0)
                
                if activity_type not in activity_types:
                    activity_types[activity_type] = {
                        "count": 0,
                        "total_duration": 0,
                        "total_distance": 0,
                        "total_calories": 0,
                        "avg_duration": 0,
                        "avg_distance": 0,
                        "avg_calories": 0
                    }
                
                activity_types[activity_type]["count"] += 1
                activity_types[activity_type]["total_duration"] += duration
                activity_types[activity_type]["total_distance"] += distance
                activity_types[activity_type]["total_calories"] += calories
                
                total_duration += duration
                total_distance += distance
                total_calories += calories
            
            # Calculate averages
            for activity_type in activity_types:
                data = activity_types[activity_type]
                count = data["count"]
                data["avg_duration"] = data["total_duration"] / count
                data["avg_distance"] = data["total_distance"] / count
                data["avg_calories"] = data["total_calories"] / count
            
            # Calculate weekly frequency
            weekly_frequency = len(activities) / (days_back / 7)
            
            # Find most common activity type
            most_common_type = max(activity_types.keys(), key=lambda x: activity_types[x]["count"]) if activity_types else "none"
            
            # Calculate performance trends
            performance_trend = self._analyze_performance_trend(activities)
            
            return {
                "total_activities": len(activities),
                "period_days": days_back,
                "weekly_frequency": weekly_frequency,
                "most_common_activity": most_common_type,
                "activity_types": activity_types,
                "totals": {
                    "duration_hours": total_duration / 3600,
                    "distance_km": total_distance,
                    "calories_burned": total_calories
                },
                "performance_trend": performance_trend
            }
            
        except Exception as e:
            self.logger.error(f"Error analyzing activity patterns for {user_id}: {e}")
            return {"error": str(e)}
    
    def _analyze_performance_trend(self, activities: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze performance trends in activities."""
        if len(activities) < 2:
            return {"trend": "insufficient_data"}
        
        # Sort by date
        sorted_activities = sorted(activities, key=lambda x: x.get("start_time", datetime.min))
        
        # Derive pace from distance/duration (sec per km) when possible.
        paces = []
        for activity in sorted_activities:
            distance_km = activity.get("distance_km") or 0
            duration_seconds = activity.get("duration_seconds") or 0
            if distance_km and duration_seconds:
                paces.append(duration_seconds / distance_km)
        
        if len(paces) >= 2:
            first_half = paces[:len(paces)//2]
            second_half = paces[len(paces)//2:]
            
            avg_first = mean(first_half)
            avg_second = mean(second_half)
            
            # Lower pace = better performance
            if avg_second < avg_first:
                pace_trend = "improving"
            elif avg_second > avg_first:
                pace_trend = "declining"
            else:
                pace_trend = "stable"
        else:
            pace_trend = "unknown"
        
        # Calculate duration trends
        durations = [activity.get("duration_seconds", 0) for activity in sorted_activities]
        duration_trend = "increasing" if durations[-1] > durations[0] else "stable" if durations[-1] == durations[0] else "decreasing"
        
        return {
            "pace_trend": pace_trend,
            "duration_trend": duration_trend,
            "data_points": len(activities)
        }
    
    async def calculate_fitness_score(self, user_id: str) -> Dict[str, Any]:
        """Calculate overall fitness score based on multiple metrics."""
        try:
            # Get recent data
            end_date = datetime.now()
            start_date = end_date - timedelta(days=30)
            
            summaries = await self.db_tools.get_daily_summaries(user_id, start_date, end_date)
            activities = await self.fetch_activity_data(user_id, 30)
            
            if not summaries:
                return {"error": "Insufficient data for fitness score calculation"}
            
            # Calculate component scores (0-100)
            activity_score = self._calculate_activity_score(activities)
            consistency_score = self._calculate_consistency_score(summaries)
            sleep_score = self._calculate_sleep_score(summaries)
            heart_rate_score = self._calculate_heart_rate_score(summaries)
            
            # Weighted overall score
            overall_score = (
                activity_score * 0.3 +
                consistency_score * 0.25 +
                sleep_score * 0.25 +
                heart_rate_score * 0.2
            )
            
            # Determine fitness level
            if overall_score >= 80:
                fitness_level = "excellent"
            elif overall_score >= 65:
                fitness_level = "good"
            elif overall_score >= 50:
                fitness_level = "fair"
            else:
                fitness_level = "needs_improvement"
            
            return {
                "overall_score": round(overall_score, 1),
                "fitness_level": fitness_level,
                "component_scores": {
                    "activity": round(activity_score, 1),
                    "consistency": round(consistency_score, 1),
                    "sleep": round(sleep_score, 1),
                    "heart_rate": round(heart_rate_score, 1)
                },
                "recommendations": self._generate_fitness_recommendations(
                    activity_score, consistency_score, sleep_score, heart_rate_score
                )
            }
            
        except Exception as e:
            self.logger.error(f"Error calculating fitness score for {user_id}: {e}")
            return {"error": str(e)}
    
    def _calculate_activity_score(self, activities: List[Dict[str, Any]]) -> float:
        """Calculate activity component score."""
        if not activities:
            return 0
        
        # Base score on frequency and variety
        weekly_frequency = len(activities) / 4  # Assuming 30 days = ~4 weeks
        frequency_score = min(100, weekly_frequency * 20)  # 5 activities per week = 100
        
        # Variety bonus
        activity_types = set(activity.get("activity_type", "unknown") for activity in activities)
        variety_score = min(20, len(activity_types) * 5)  # Up to 20 bonus points
        
        return min(100, frequency_score + variety_score)
    
    def _calculate_consistency_score(self, summaries: List[Dict[str, Any]]) -> float:
        """Calculate consistency component score."""
        if not summaries:
            return 0
        
        # Calculate consistency based on daily step variation
        steps = [summary.get("steps", 0) for summary in summaries if summary.get("steps")]
        if not steps:
            return 0
        
        avg_steps = mean(steps)
        if avg_steps == 0:
            return 0
        
        std_dev = stdev(steps) if len(steps) > 1 else 0
        consistency = max(0, 100 - (std_dev / avg_steps * 100))
        
        return consistency
    
    def _calculate_sleep_score(self, summaries: List[Dict[str, Any]]) -> float:
        """Calculate sleep component score."""
        sleep_durations = [
            summary.get("sleep_duration_hours", 0) for summary in summaries 
            if summary.get("sleep_duration_hours")
        ]
        
        if not sleep_durations:
            return 50  # Default score if no sleep data
        
        avg_sleep = mean(sleep_durations)
        
        # Optimal sleep is 7-9 hours
        if 7 <= avg_sleep <= 9:
            return 100
        elif 6 <= avg_sleep < 7 or 9 < avg_sleep <= 10:
            return 80
        elif 5 <= avg_sleep < 6 or 10 < avg_sleep <= 11:
            return 60
        else:
            return 30
    
    def _calculate_heart_rate_score(self, summaries: List[Dict[str, Any]]) -> float:
        """Calculate heart rate component score."""
        resting_hrs = [
            summary.get("resting_heart_rate", 0) for summary in summaries 
            if summary.get("resting_heart_rate")
        ]
        
        if not resting_hrs:
            return 50  # Default score if no HR data
        
        avg_rhr = mean(resting_hrs)
        
        # Score based on typical resting HR ranges
        if avg_rhr <= 55:
            return 100  # Excellent
        elif avg_rhr <= 65:
            return 85   # Good
        elif avg_rhr <= 75:
            return 70   # Fair
        else:
            return 50   # Needs improvement
    
    def _generate_fitness_recommendations(self, activity_score: float, consistency_score: float, 
                                        sleep_score: float, heart_rate_score: float) -> List[str]:
        """Generate personalized fitness recommendations."""
        recommendations = []
        
        if activity_score < 60:
            recommendations.append("Increase your weekly activity frequency to 4-5 sessions")
        
        if consistency_score < 60:
            recommendations.append("Focus on maintaining consistent daily activity levels")
        
        if sleep_score < 70:
            recommendations.append("Aim for 7-9 hours of quality sleep each night")
        
        if heart_rate_score < 70:
            recommendations.append("Include more cardio exercise to improve heart health")
        
        if not recommendations:
            recommendations.append("Keep up the excellent work! Consider setting new challenge goals")
        
        return recommendations
    
    # Data Quality Tools
    
    async def assess_data_quality(self, user_id: str, days_back: int = 7) -> Dict[str, Any]:
        """Assess the quality and completeness of user data."""
        try:
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days_back)
            
            summaries = await self.db_tools.get_daily_summaries(user_id, start_date, end_date)
            activities = await self.fetch_activity_data(user_id, days_back)
            
            # Calculate completeness scores
            expected_days = days_back
            actual_days = len(summaries)
            completeness_score = (actual_days / expected_days) * 100
            
            # Check data freshness
            if summaries:
                latest_data = max(summary.get("date", datetime.min) for summary in summaries)
                days_since_last = (datetime.now() - latest_data).days
                freshness_score = max(0, 100 - (days_since_last * 20))
            else:
                freshness_score = 0
            
            # Check data variety
            metrics_available = []
            if summaries:
                sample_summary = summaries[0]
                for metric in ["steps", "sleep_duration_hours", "resting_heart_rate", "calories_burned"]:
                    if sample_summary.get(metric) is not None:
                        metrics_available.append(metric)
            
            variety_score = (len(metrics_available) / 4) * 100
            
            return {
                "overall_quality": round((completeness_score + freshness_score + variety_score) / 3, 1),
                "completeness_score": round(completeness_score, 1),
                "freshness_score": round(freshness_score, 1),
                "variety_score": round(variety_score, 1),
                "data_summary": {
                    "days_with_data": actual_days,
                    "expected_days": expected_days,
                    "total_activities": len(activities),
                    "metrics_available": metrics_available,
                    "last_sync": latest_data if summaries else None
                }
            }
            
        except Exception as e:
            self.logger.error(f"Error assessing data quality for {user_id}: {e}")
            return {"error": str(e)}


def get_data_tools(garmin_client: GarminClient = None, db_tools: DatabaseTools = None, config: Config = None) -> DataTools:
    """Get or create data tools instance."""
    if not hasattr(get_data_tools, '_instance'):
        if not all([garmin_client, db_tools, config]):
            raise ValueError("garmin_client, db_tools, and config are required for first initialization")
        get_data_tools._instance = DataTools(garmin_client, db_tools, config)
    return get_data_tools._instance


def init_data_tools(garmin_client: GarminClient, db_tools: DatabaseTools, config: Config) -> DataTools:
    """Initialize and return data tools instance."""
    tools = DataTools(garmin_client, db_tools, config)
    get_data_tools._instance = tools
    return tools 