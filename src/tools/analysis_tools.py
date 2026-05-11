"""
Analysis Tools for AI Coach Agent
=================================

This module provides advanced analysis and insights tools for the AI coaching agent.
Handles complex data analysis and pattern recognition.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
import numpy as np
from statistics import mean, median, stdev, mode

from core.config import Config
from tools.data_tools import DataTools
from tools.db_tools import DatabaseTools


logger = logging.getLogger(__name__)


class AnalysisTools:
    """
    Advanced analysis tools for the AI coaching agent.
    
    Provides:
    - Trend analysis and predictions
    - Performance pattern recognition
    - Goal achievement analysis
    - Comparative benchmarking
    - Health insights and recommendations
    """
    
    def __init__(self, data_tools: DataTools, db_tools: DatabaseTools, config: Config):
        """Initialize analysis tools."""
        self.data_tools = data_tools
        self.db_tools = db_tools
        self.config = config
        self.logger = logging.getLogger(__name__)
    
    # Trend Analysis Tools
    
    async def analyze_multi_metric_trends(self, user_id: str, days_back: int = 30) -> Dict[str, Any]:
        """Analyze trends across multiple metrics simultaneously."""
        try:
            # Define key metrics to analyze
            metrics = ["steps", "sleep_duration_hours", "resting_heart_rate", "calories_burned"]
            
            trends = {}
            correlations = {}
            
            # Get trend data for each metric
            for metric in metrics:
                trend_data = await self.data_tools.process_daily_trends(user_id, metric, days_back)
                if "error" not in trend_data:
                    trends[metric] = trend_data
            
            # Calculate correlations between metrics
            if len(trends) >= 2:
                correlations = await self._calculate_metric_correlations(user_id, list(trends.keys()), days_back)
            
            # Generate insights
            insights = self._generate_multi_metric_insights(trends, correlations)
            
            return {
                "period_days": days_back,
                "metrics_analyzed": list(trends.keys()),
                "trends": trends,
                "correlations": correlations,
                "insights": insights,
                "overall_trend": self._determine_overall_trend(trends)
            }
            
        except Exception as e:
            self.logger.error(f"Error analyzing multi-metric trends for {user_id}: {e}")
            return {"error": str(e)}
    
    async def _calculate_metric_correlations(self, user_id: str, metrics: List[str], days_back: int) -> Dict[str, Any]:
        """Calculate correlations between different metrics."""
        try:
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days_back)
            
            summaries = await self.db_tools.get_daily_summaries(user_id, start_date, end_date)
            if not summaries:
                return {}
            
            # Extract metric values
            metric_data = {}
            for metric in metrics:
                values = [summary.get(metric) for summary in summaries if summary.get(metric) is not None]
                if len(values) >= 7:  # Need at least a week of data
                    metric_data[metric] = values
            
            # Calculate correlations
            correlations = {}
            for i, metric1 in enumerate(metric_data.keys()):
                for j, metric2 in enumerate(metric_data.keys()):
                    if i < j:  # Avoid duplicate pairs
                        correlation = self._calculate_correlation(metric_data[metric1], metric_data[metric2])
                        correlations[f"{metric1}_vs_{metric2}"] = {
                            "correlation": correlation,
                            "strength": self._interpret_correlation_strength(correlation),
                            "relationship": self._interpret_correlation_relationship(correlation)
                        }
            
            return correlations
            
        except Exception as e:
            self.logger.error(f"Error calculating metric correlations: {e}")
            return {}
    
    def _calculate_correlation(self, values1: List[float], values2: List[float]) -> float:
        """Calculate Pearson correlation coefficient."""
        if len(values1) != len(values2) or len(values1) < 2:
            return 0.0
        
        # Ensure same length
        min_len = min(len(values1), len(values2))
        values1 = values1[:min_len]
        values2 = values2[:min_len]
        
        try:
            return np.corrcoef(values1, values2)[0, 1]
        except:
            return 0.0
    
    def _interpret_correlation_strength(self, correlation: float) -> str:
        """Interpret correlation strength."""
        abs_corr = abs(correlation)
        if abs_corr >= 0.8:
            return "very_strong"
        elif abs_corr >= 0.6:
            return "strong"
        elif abs_corr >= 0.4:
            return "moderate"
        elif abs_corr >= 0.2:
            return "weak"
        else:
            return "very_weak"
    
    def _interpret_correlation_relationship(self, correlation: float) -> str:
        """Interpret correlation relationship."""
        if correlation > 0.1:
            return "positive"
        elif correlation < -0.1:
            return "negative"
        else:
            return "no_relationship"
    
    def _generate_multi_metric_insights(self, trends: Dict[str, Any], correlations: Dict[str, Any]) -> List[str]:
        """Generate insights from multi-metric trends."""
        insights = []
        
        # Analyze individual trends
        improving_metrics = []
        declining_metrics = []
        
        for metric, trend_data in trends.items():
            if trend_data.get("trend_direction") == "increasing":
                # Determine if increasing is good or bad for this metric
                if metric in ["steps", "sleep_duration_hours", "calories_burned"]:
                    improving_metrics.append(metric)
                elif metric in ["resting_heart_rate"]:
                    declining_metrics.append(metric)
            elif trend_data.get("trend_direction") == "decreasing":
                if metric in ["steps", "sleep_duration_hours", "calories_burned"]:
                    declining_metrics.append(metric)
                elif metric in ["resting_heart_rate"]:
                    improving_metrics.append(metric)
        
        # Generate insights based on trends
        if improving_metrics:
            insights.append(f"Great progress in {', '.join(improving_metrics)}! Your consistency is paying off.")
        
        if declining_metrics:
            insights.append(f"Focus area identified: {', '.join(declining_metrics)} could use attention.")
        
        # Analyze correlations
        for corr_name, corr_data in correlations.items():
            if corr_data["strength"] in ["strong", "very_strong"]:
                relationship = corr_data["relationship"]
                strength = corr_data["strength"]
                metrics = corr_name.replace("_vs_", " and ").replace("_", " ")
                
                if relationship == "positive":
                    insights.append(f"Strong positive connection found between {metrics}.")
                elif relationship == "negative":
                    insights.append(f"Interesting inverse relationship between {metrics}.")
        
        return insights
    
    def _determine_overall_trend(self, trends: Dict[str, Any]) -> str:
        """Determine overall fitness trend."""
        if not trends:
            return "insufficient_data"
        
        trend_scores = []
        for metric, trend_data in trends.items():
            direction = trend_data.get("trend_direction", "stable")
            strength = trend_data.get("trend_strength", "weak")
            
            # Score based on direction (good metrics increase, bad metrics decrease)
            if metric in ["steps", "sleep_duration_hours", "calories_burned"]:
                if direction == "increasing":
                    score = 2 if strength == "strong" else 1
                elif direction == "decreasing":
                    score = -2 if strength == "strong" else -1
                else:
                    score = 0
            elif metric in ["resting_heart_rate"]:
                if direction == "decreasing":
                    score = 2 if strength == "strong" else 1
                elif direction == "increasing":
                    score = -2 if strength == "strong" else -1
                else:
                    score = 0
            else:
                score = 0
            
            trend_scores.append(score)
        
        avg_score = mean(trend_scores) if trend_scores else 0
        
        if avg_score >= 1:
            return "improving"
        elif avg_score <= -1:
            return "declining"
        else:
            return "stable"
    
    # Performance Analysis Tools
    
    async def analyze_performance_peaks(self, user_id: str, days_back: int = 90) -> Dict[str, Any]:
        """Analyze performance peaks and patterns."""
        try:
            activities = await self.data_tools.fetch_activity_data(user_id, days_back)
            
            if not activities:
                return {"error": "No activity data available"}
            
            # Group activities by week
            weekly_performance = {}
            for activity in activities:
                start_time = activity.get("start_time", datetime.min)
                week_key = start_time.strftime("%Y-W%U")
                
                if week_key not in weekly_performance:
                    weekly_performance[week_key] = {
                        "activities": [],
                        "total_distance": 0,
                        "total_duration": 0,
                        "total_calories": 0,
                        "avg_heart_rate": []
                    }
                
                weekly_performance[week_key]["activities"].append(activity)
                weekly_performance[week_key]["total_distance"] += (activity.get("distance_km", 0) or 0) * 1000
                weekly_performance[week_key]["total_duration"] += activity.get("duration_seconds", 0)
                weekly_performance[week_key]["total_calories"] += activity.get("calories_burned", 0)
                
                if activity.get("avg_heart_rate"):
                    weekly_performance[week_key]["avg_heart_rate"].append(activity.get("avg_heart_rate"))
            
            # Calculate weekly averages
            for week_data in weekly_performance.values():
                week_data["avg_hr"] = mean(week_data["avg_heart_rate"]) if week_data["avg_heart_rate"] else 0
                week_data["activity_count"] = len(week_data["activities"])
            
            # Find peak performance week
            peak_week = max(weekly_performance.keys(), 
                          key=lambda x: weekly_performance[x]["total_distance"] + weekly_performance[x]["total_duration"])
            
            # Calculate performance consistency
            weekly_distances = [data["total_distance"] for data in weekly_performance.values()]
            consistency_score = self._calculate_performance_consistency(weekly_distances)
            
            # Identify patterns
            patterns = self._identify_performance_patterns(weekly_performance)
            
            return {
                "period_days": days_back,
                "weeks_analyzed": len(weekly_performance),
                "peak_week": peak_week,
                "peak_performance": weekly_performance[peak_week],
                "consistency_score": consistency_score,
                "patterns": patterns,
                "weekly_summary": weekly_performance
            }
            
        except Exception as e:
            self.logger.error(f"Error analyzing performance peaks for {user_id}: {e}")
            return {"error": str(e)}
    
    def _calculate_performance_consistency(self, weekly_values: List[float]) -> float:
        """Calculate performance consistency score."""
        if len(weekly_values) < 2:
            return 0
        
        avg_value = mean(weekly_values)
        if avg_value == 0:
            return 0
        
        std_dev = stdev(weekly_values)
        consistency = max(0, 100 - (std_dev / avg_value * 100))
        
        return round(consistency, 1)
    
    def _identify_performance_patterns(self, weekly_performance: Dict[str, Any]) -> List[str]:
        """Identify patterns in performance data."""
        patterns = []
        
        # Sort weeks chronologically
        sorted_weeks = sorted(weekly_performance.keys())
        
        if len(sorted_weeks) < 4:
            return ["Insufficient data for pattern analysis"]
        
        # Check for improvement trend
        first_half = sorted_weeks[:len(sorted_weeks)//2]
        second_half = sorted_weeks[len(sorted_weeks)//2:]
        
        first_avg = mean([weekly_performance[week]["total_distance"] for week in first_half])
        second_avg = mean([weekly_performance[week]["total_distance"] for week in second_half])
        
        if second_avg > first_avg * 1.1:  # 10% improvement
            patterns.append("Consistent improvement in training volume")
        elif second_avg < first_avg * 0.9:  # 10% decline
            patterns.append("Training volume has decreased recently")
        
        # Check for weekly consistency
        activity_counts = [weekly_performance[week]["activity_count"] for week in sorted_weeks]
        if len(set(activity_counts)) <= 2:  # Very similar activity counts
            patterns.append("Excellent consistency in workout frequency")
        
        return patterns
    
    # Goal Analysis Tools
    
    async def analyze_goal_achievement_likelihood(self, user_id: str, goal_id: str) -> Dict[str, Any]:
        """Analyze likelihood of achieving a specific goal."""
        try:
            # Get goal details
            profile = await self.db_tools.get_user_profile(user_id)
            if not profile:
                return {"error": "User profile not found"}
            
            goal = next((g for g in profile.get("goals", []) if g["id"] == goal_id), None)
            if not goal:
                return {"error": "Goal not found"}
            
            # Get recent performance data
            end_date = datetime.now()
            start_date = end_date - timedelta(days=30)
            
            summaries = await self.db_tools.get_daily_summaries(user_id, start_date, end_date)
            
            if not summaries:
                return {"error": "No performance data available"}
            
            # Calculate current progress rate
            goal_type = goal["goal_type"]
            current_value = goal["current_value"]
            target_value = goal["target_value"]
            target_date = goal.get("target_date")
            
            if not target_date:
                return {"error": "Goal has no target date"}
            
            # Calculate time remaining
            days_remaining = (target_date - datetime.now()).days
            if days_remaining <= 0:
                return {"error": "Goal target date has passed"}
            
            # Get recent performance for this goal type
            recent_values = [summary.get(goal_type, 0) for summary in summaries[-7:]]  # Last 7 days
            recent_avg = mean(recent_values) if recent_values else 0
            
            # Calculate required daily progress
            progress_needed = target_value - current_value
            required_daily_progress = progress_needed / days_remaining
            
            # Calculate likelihood based on recent performance
            if goal_type == "steps":
                likelihood = self._calculate_steps_goal_likelihood(recent_avg, required_daily_progress)
            elif goal_type == "weight":
                likelihood = self._calculate_weight_goal_likelihood(recent_values, required_daily_progress)
            else:
                likelihood = self._calculate_generic_goal_likelihood(recent_avg, required_daily_progress)
            
            # Generate recommendations
            recommendations = self._generate_goal_recommendations(goal, likelihood, required_daily_progress)
            
            return {
                "goal": goal,
                "current_progress": current_value,
                "target_value": target_value,
                "progress_percentage": goal["progress_percentage"],
                "days_remaining": days_remaining,
                "required_daily_progress": required_daily_progress,
                "recent_daily_average": recent_avg,
                "achievement_likelihood": likelihood,
                "recommendations": recommendations
            }
            
        except Exception as e:
            self.logger.error(f"Error analyzing goal achievement likelihood: {e}")
            return {"error": str(e)}
    
    def _calculate_steps_goal_likelihood(self, recent_avg: float, required_daily_progress: float) -> Dict[str, Any]:
        """Calculate likelihood for steps goal."""
        if recent_avg >= required_daily_progress:
            probability = min(95, 85 + (recent_avg - required_daily_progress) / required_daily_progress * 10)
            level = "high"
        elif recent_avg >= required_daily_progress * 0.8:
            probability = 70
            level = "moderate"
        elif recent_avg >= required_daily_progress * 0.6:
            probability = 50
            level = "low"
        else:
            probability = 30
            level = "very_low"
        
        return {
            "probability": round(probability, 1),
            "level": level,
            "confidence": "high" if recent_avg > 0 else "low"
        }
    
    def _calculate_weight_goal_likelihood(self, recent_values: List[float], required_daily_progress: float) -> Dict[str, Any]:
        """Calculate likelihood for weight goal."""
        if len(recent_values) < 3:
            return {"probability": 50, "level": "unknown", "confidence": "low"}
        
        # Calculate recent trend
        recent_trend = (recent_values[-1] - recent_values[0]) / len(recent_values)
        
        # Weight goals usually require negative progress (weight loss)
        if required_daily_progress < 0:  # Weight loss goal
            if recent_trend <= required_daily_progress:
                probability = 80
                level = "high"
            elif recent_trend <= required_daily_progress * 0.5:
                probability = 60
                level = "moderate"
            else:
                probability = 40
                level = "low"
        else:  # Weight gain goal
            if recent_trend >= required_daily_progress:
                probability = 80
                level = "high"
            elif recent_trend >= required_daily_progress * 0.5:
                probability = 60
                level = "moderate"
            else:
                probability = 40
                level = "low"
        
        return {
            "probability": round(probability, 1),
            "level": level,
            "confidence": "high"
        }
    
    def _calculate_generic_goal_likelihood(self, recent_avg: float, required_daily_progress: float) -> Dict[str, Any]:
        """Calculate likelihood for generic goals."""
        if recent_avg >= required_daily_progress:
            probability = 75
            level = "high"
        elif recent_avg >= required_daily_progress * 0.7:
            probability = 60
            level = "moderate"
        else:
            probability = 45
            level = "low"
        
        return {
            "probability": round(probability, 1),
            "level": level,
            "confidence": "moderate"
        }
    
    def _generate_goal_recommendations(self, goal: Dict[str, Any], likelihood: Dict[str, Any], 
                                     required_daily_progress: float) -> List[str]:
        """Generate recommendations for goal achievement."""
        recommendations = []
        
        goal_type = goal["goal_type"]
        probability = likelihood["probability"]
        
        if probability >= 70:
            recommendations.append(f"You're on track! Keep up your current pace.")
        elif probability >= 50:
            recommendations.append(f"Good progress, but consider increasing effort slightly.")
        else:
            recommendations.append(f"Goal achievement requires significant effort increase.")
        
        # Specific recommendations by goal type
        if goal_type == "steps":
            if required_daily_progress > 10000:
                recommendations.append("Consider breaking your daily step goal into smaller chunks throughout the day.")
            recommendations.append("Try taking the stairs or parking farther away to increase daily steps.")
        
        elif goal_type == "weight":
            if required_daily_progress < 0:  # Weight loss
                recommendations.append("Focus on consistent calorie deficit through diet and exercise.")
            else:  # Weight gain
                recommendations.append("Consider increasing calorie intake with healthy, nutrient-dense foods.")
        
        return recommendations
    
    # Comparative Analysis Tools
    
    async def analyze_weekly_comparison(self, user_id: str, weeks_back: int = 4) -> Dict[str, Any]:
        """Compare performance across recent weeks."""
        try:
            end_date = datetime.now()
            start_date = end_date - timedelta(weeks=weeks_back)
            
            summaries = await self.db_tools.get_daily_summaries(user_id, start_date, end_date)
            
            if not summaries:
                return {"error": "No data available for comparison"}
            
            # Group by week
            weekly_data = {}
            for summary in summaries:
                date = summary.get("date", datetime.min)
                week_key = date.strftime("%Y-W%U")
                
                if week_key not in weekly_data:
                    weekly_data[week_key] = {
                        "steps": [],
                        "sleep_duration_hours": [],
                        "resting_heart_rate": [],
                        "calories_burned": []
                    }
                
                # Add data to weekly buckets
                for metric in weekly_data[week_key].keys():
                    value = summary.get(metric)
                    if value is not None:
                        weekly_data[week_key][metric].append(value)
            
            # Calculate weekly averages
            weekly_averages = {}
            for week, data in weekly_data.items():
                weekly_averages[week] = {}
                for metric, values in data.items():
                    if values:
                        weekly_averages[week][metric] = {
                            "average": mean(values),
                            "days_with_data": len(values)
                        }
            
            # Compare weeks
            comparison_insights = self._generate_weekly_comparison_insights(weekly_averages)
            
            return {
                "weeks_analyzed": len(weekly_averages),
                "weekly_averages": weekly_averages,
                "comparison_insights": comparison_insights,
                "trend_summary": self._summarize_weekly_trends(weekly_averages)
            }
            
        except Exception as e:
            self.logger.error(f"Error analyzing weekly comparison for {user_id}: {e}")
            return {"error": str(e)}
    
    def _generate_weekly_comparison_insights(self, weekly_averages: Dict[str, Any]) -> List[str]:
        """Generate insights from weekly comparison."""
        insights = []
        
        if len(weekly_averages) < 2:
            return ["Need at least 2 weeks of data for comparison"]
        
        # Compare most recent week with previous
        sorted_weeks = sorted(weekly_averages.keys())
        current_week = sorted_weeks[-1]
        previous_week = sorted_weeks[-2]
        
        current_data = weekly_averages[current_week]
        previous_data = weekly_averages[previous_week]
        
        # Compare each metric
        for metric in ["steps", "sleep_duration_hours", "resting_heart_rate"]:
            if metric in current_data and metric in previous_data:
                current_val = current_data[metric]["average"]
                previous_val = previous_data[metric]["average"]
                
                change_pct = ((current_val - previous_val) / previous_val) * 100
                
                if abs(change_pct) >= 5:  # Significant change
                    direction = "increased" if change_pct > 0 else "decreased"
                    
                    if metric == "steps":
                        insights.append(f"Daily steps {direction} by {abs(change_pct):.1f}% this week")
                    elif metric == "sleep_duration_hours":
                        insights.append(f"Sleep duration {direction} by {abs(change_pct):.1f}% this week")
                    elif metric == "resting_heart_rate":
                        trend = "improved" if change_pct < 0 else "increased"
                        insights.append(f"Resting heart rate {trend} by {abs(change_pct):.1f}% this week")
        
        return insights
    
    def _summarize_weekly_trends(self, weekly_averages: Dict[str, Any]) -> Dict[str, str]:
        """Summarize trends across all weeks."""
        if len(weekly_averages) < 3:
            return {"trend": "insufficient_data"}
        
        trends = {}
        sorted_weeks = sorted(weekly_averages.keys())
        
        for metric in ["steps", "sleep_duration_hours", "resting_heart_rate"]:
            values = []
            for week in sorted_weeks:
                if metric in weekly_averages[week]:
                    values.append(weekly_averages[week][metric]["average"])
            
            if len(values) >= 3:
                first_val = values[0]
                last_val = values[-1]
                change = ((last_val - first_val) / first_val) * 100
                
                if abs(change) >= 10:
                    trends[metric] = "increasing" if change > 0 else "decreasing"
                else:
                    trends[metric] = "stable"
            else:
                trends[metric] = "insufficient_data"
        
        return trends


def get_analysis_tools(data_tools: DataTools = None, db_tools: DatabaseTools = None, config: Config = None) -> AnalysisTools:
    """Get or create analysis tools instance."""
    if not hasattr(get_analysis_tools, '_instance'):
        if not all([data_tools, db_tools, config]):
            raise ValueError("data_tools, db_tools, and config are required for first initialization")
        get_analysis_tools._instance = AnalysisTools(data_tools, db_tools, config)
    return get_analysis_tools._instance


def init_analysis_tools(data_tools: DataTools, db_tools: DatabaseTools, config: Config) -> AnalysisTools:
    """Initialize and return analysis tools instance."""
    tools = AnalysisTools(data_tools, db_tools, config)
    get_analysis_tools._instance = tools
    return tools 