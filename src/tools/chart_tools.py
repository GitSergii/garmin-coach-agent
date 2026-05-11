"""
Chart Tools for AI Coach Agent
==============================

Generate static chart images for Telegram delivery and AI analysis context.
"""

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Any, List

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd

from core.config import Config
from tools.data_tools import DataTools


logger = logging.getLogger(__name__)

# Shared colour palette used across all charts
_PALETTE = {
    "primary": "#2EC4C7",
    "secondary": "#FF6B6B",
    "green": "#4CAF50",
    "orange": "#FFB347",
    "purple": "#6A4C93",
    "red": "#E05252",
    "teal": "#1A9E9E",
    "bar": "#8DD3C7",
}

# Maps metric column names → human label + colour
_METRIC_META: Dict[str, Dict[str, str]] = {
    "steps":                 {"label": "Steps",              "color": _PALETTE["primary"]},
    "calories_burned":       {"label": "Calories Burned",    "color": _PALETTE["secondary"]},
    "distance_km":           {"label": "Distance (km)",      "color": _PALETTE["teal"]},
    "active_minutes":        {"label": "Active Minutes",     "color": _PALETTE["orange"]},
    "sleep_duration_hours":  {"label": "Sleep (hours)",      "color": _PALETTE["green"]},
    "sleep_quality_score":   {"label": "Sleep Quality",      "color": "#81C784"},
    "resting_heart_rate":    {"label": "Resting HR (bpm)",   "color": _PALETTE["red"]},
    "avg_heart_rate":        {"label": "Avg HR (bpm)",       "color": "#EF9A9A"},
    "stress_level_avg":      {"label": "Stress Level",       "color": _PALETTE["purple"]},
    "body_battery_level":    {"label": "Body Battery",       "color": "#FFD54F"},
    "vo2_max":               {"label": "VO2 Max",            "color": "#42A5F5"},
}


def _apply_style(fig: plt.Figure, axes) -> None:
    """Apply consistent visual style to any chart figure."""
    fig.patch.set_facecolor("#F9F9F9")
    ax_list = axes if hasattr(axes, "__iter__") else [axes]
    for ax in ax_list:
        ax.set_facecolor("#FAFAFA")
        ax.grid(alpha=0.2, linestyle="--")
        ax.tick_params(labelsize=8)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)


def _save_chart(fig: plt.Figure, output_dir: Path, prefix: str) -> str:
    """Save figure to disk and return the path string."""
    chart_path = output_dir / f"{prefix}_{int(datetime.now().timestamp())}.png"
    fig.savefig(chart_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return str(chart_path)


def _parse_chart_spec(spec_str: str) -> Dict[str, str]:
    """Parse 'key=value,key=value' spec string into a dict."""
    result: Dict[str, str] = {}
    for part in spec_str.split(","):
        part = part.strip()
        if "=" in part:
            k, _, v = part.partition("=")
            result[k.strip().lower()] = v.strip()
        elif part:
            # bare word treated as metric name if it matches known column
            candidate = part.lower().replace(" ", "_")
            if candidate in _METRIC_META:
                result.setdefault("metric", candidate)
    return result


class ChartTools:
    """Chart generation utility for fitness visualizations."""

    def __init__(self, data_tools: DataTools, config: Config):
        self.data_tools = data_tools
        self.config = config
        self.logger = logging.getLogger(__name__)
        self.output_dir = Path("data/generated_charts")
        self.output_dir.mkdir(parents=True, exist_ok=True)

    async def generate_multi_metric_dashboard(self, user_id: str, days_back: int = 30) -> Dict[str, Any]:
        """Generate multi-panel performance dashboard chart."""
        try:
            end_date = datetime.now(timezone.utc)
            start_date = end_date - timedelta(days=days_back)
            summaries = await self.data_tools.db_tools.get_daily_summaries(user_id, start_date, end_date)
            if not summaries:
                return {"error": "No summary data available for chart generation"}

            df = pd.DataFrame(summaries)
            if df.empty:
                return {"error": "No chartable data available"}

            if "date" in df.columns:
                df["date"] = pd.to_datetime(df["date"], utc=True).dt.tz_convert(None)
                df = df.sort_values("date")
            else:
                return {"error": "Missing date field in summary data"}

            fig, axes = plt.subplots(3, 1, figsize=(14, 11), sharex=True)
            _apply_style(fig, axes)

            # --- Panel 1: Steps (area) + Calories (line) ---
            steps = df.get("steps", pd.Series([0] * len(df))).fillna(0)
            calories = df.get("calories_burned", pd.Series([0] * len(df))).fillna(0)
            axes[0].fill_between(df["date"], steps, alpha=0.25, color="#2EC4C7")
            axes[0].plot(df["date"], steps, color="#2EC4C7", linewidth=2, label="Steps")
            axes[0].set_ylabel("Steps")
            axes[0].set_title("Daily Steps & Calories", fontsize=10, pad=4)
            axes[0].grid(alpha=0.2)
            axes[0].legend(loc="upper left", fontsize=8)
            ax0b = axes[0].twinx()
            ax0b.plot(df["date"], calories, color="#FF6B6B", linewidth=1.8, label="Calories", alpha=0.85)
            ax0b.set_ylabel("Calories")
            ax0b.legend(loc="upper right", fontsize=8)

            # --- Panel 2: Sleep (bars) + Resting HR (red line + baseline) ---
            sleep = df.get("sleep_duration_hours", pd.Series([0] * len(df))).fillna(0)
            rhr = df.get("resting_heart_rate", pd.Series([None] * len(df)))
            rhr_clean = rhr.dropna()

            axes[1].bar(df["date"], sleep, color="#4CAF50", alpha=0.65, label="Sleep (h)", width=0.8)
            axes[1].set_ylabel("Sleep Hours")
            axes[1].set_title("Sleep Quality & Resting Heart Rate", fontsize=10, pad=4)
            axes[1].grid(alpha=0.2)
            axes[1].legend(loc="upper left", fontsize=8)

            ax1b = axes[1].twinx()
            ax1b.plot(df["date"], rhr, color="#E05252", linewidth=2, marker=".", markersize=4, label="Resting HR")
            ax1b.set_ylabel("Resting HR (bpm)")
            if len(rhr_clean) > 0:
                baseline_hr = round(rhr_clean.mean(), 1)
                ax1b.axhline(y=baseline_hr, color="#E05252", linestyle="--", alpha=0.35, linewidth=1)
                ax1b.annotate(
                    f"avg {baseline_hr}",
                    xy=(df["date"].iloc[-1], baseline_hr),
                    xytext=(4, 4),
                    textcoords="offset points",
                    fontsize=7,
                    color="#E05252",
                    alpha=0.75,
                )
            ax1b.legend(loc="upper right", fontsize=8)

            # --- Panel 3: Distance (bars) + 7-day rolling avg + Active Minutes ---
            distance = df.get("distance_km", pd.Series([0] * len(df))).fillna(0)
            active_min = df.get("active_minutes", pd.Series([0] * len(df))).fillna(0)
            rolling_dist = distance.rolling(window=7, min_periods=1).mean()

            axes[2].bar(df["date"], distance, color="#8DD3C7", alpha=0.75, label="Distance (km)", width=0.8)
            axes[2].plot(df["date"], rolling_dist, color="#1A9E9E", linewidth=2, linestyle="-", label="7-day avg distance")
            axes[2].set_ylabel("Distance (km) / Minutes")
            axes[2].set_title("Activity Distance & Active Minutes", fontsize=10, pad=4)
            axes[2].grid(alpha=0.2)

            ax2b = axes[2].twinx()
            ax2b.plot(df["date"], active_min, color="#FFB347", linewidth=1.8, label="Active Min", alpha=0.9)
            ax2b.set_ylabel("Active Minutes")

            lines2, labels2 = axes[2].get_legend_handles_labels()
            lines2b, labels2b = ax2b.get_legend_handles_labels()
            axes[2].legend(lines2 + lines2b, labels2 + labels2b, loc="upper left", fontsize=8)
            axes[2].set_xlabel("Date")

            fig.suptitle("GarminCoach Performance Dashboard", fontsize=14, fontweight="bold", y=1.01)
            fig.autofmt_xdate()
            fig.tight_layout()

            path = _save_chart(fig, self.output_dir, f"dashboard_{user_id}")
            return {
                "chart_type": "multi_metric_dashboard",
                "chart_path": path,
                "caption": "Multi-metric performance dashboard (steps, calories, sleep, HR, distance).",
                "points": len(df),
                "period_days": days_back,
                "generated_at": datetime.now().isoformat(),
            }
        except Exception as e:
            self.logger.error(f"Error generating dashboard chart for {user_id}: {e}")
            return {"error": str(e)}

    async def generate_running_activity_chart(self, user_id: str, activity_id: str) -> Dict[str, Any]:
        """Generate a chart for one running activity using splits/detail data."""
        try:
            detail = await self.data_tools.fetch_activity_details(user_id, activity_id)
            if not detail:
                return {"error": "Activity details not found"}

            splits = detail.get("splits") or []
            if not splits:
                return {"error": "No split data available for this activity"}

            split_df = pd.DataFrame(splits)
            if split_df.empty:
                return {"error": "Split data empty"}

            split_idx = list(range(1, len(split_df) + 1))
            distance = split_df.get("distance", pd.Series([0] * len(split_df)))
            moving_duration = split_df.get("movingDuration", pd.Series([0] * len(split_df)))
            pace_sec_per_km = moving_duration / (distance / 1000).replace(0, pd.NA)

            fig, axes = plt.subplots(2, 1, figsize=(12, 8), sharex=True)
            _apply_style(fig, axes)

            axes[0].plot(split_idx, pace_sec_per_km, color=_PALETTE["purple"], marker="o", linewidth=2)
            axes[0].set_ylabel("Pace (sec/km)", fontsize=9)
            axes[0].set_title("Split Pace", fontsize=10, pad=4)

            hr = split_df.get("averageHR", pd.Series([0] * len(split_df)))
            axes[1].bar(split_idx, hr, color=_PALETTE["secondary"], alpha=0.85)
            axes[1].set_ylabel("Avg HR", fontsize=9)
            axes[1].set_xlabel("Split", fontsize=9)
            axes[1].set_title("Split Heart Rate", fontsize=10, pad=4)

            fig.suptitle(f"Running Activity — {activity_id}", fontsize=13, fontweight="bold")
            fig.tight_layout()

            path = _save_chart(fig, self.output_dir, f"run_activity_{activity_id}")
            return {
                "chart_type": "running_activity_detail",
                "chart_path": path,
                "caption": f"Running activity {activity_id}: pace and heart-rate by split.",
                "activity_id": activity_id,
                "generated_at": datetime.now().isoformat(),
            }
        except Exception as e:
            self.logger.error(f"Error generating running activity chart for {user_id}, {activity_id}: {e}")
            return {"error": str(e)}

    # Metrics that represent discrete nightly/daily events — bars are clearer than lines
    _BAR_METRICS = {"sleep_duration_hours", "sleep_quality_score"}

    async def generate_metric_trend(
        self,
        user_id: str,
        metric: str,
        days: int = 14,
        title: str = "",
        use_bars: bool = False,
    ) -> Dict[str, Any]:
        """Plot any single daily metric as a trend chart (line+area or bars for discrete metrics)."""
        try:
            end_date = datetime.now(timezone.utc)
            start_date = end_date - timedelta(days=days)
            summaries = await self.data_tools.db_tools.get_daily_summaries(user_id, start_date, end_date)
            if not summaries:
                return {"error": "No summary data available"}

            df = pd.DataFrame(summaries)
            if df.empty or metric not in df.columns:
                available = [k for k in _METRIC_META if k in df.columns]
                return {"error": f"Metric '{metric}' not found. Available: {available}"}

            df["date"] = pd.to_datetime(df["date"], utc=True).dt.tz_convert(None)
            df = df.sort_values("date")
            series = df[metric].ffill().fillna(0)

            meta = _METRIC_META.get(metric, {"label": metric, "color": _PALETTE["primary"]})
            chart_title = title or f"{meta['label']} — last {days} days"
            as_bars = use_bars or metric in self._BAR_METRICS

            fig, ax = plt.subplots(figsize=(12, 5))
            _apply_style(fig, [ax])

            if as_bars:
                ax.bar(df["date"], series, color=meta["color"], alpha=0.7,
                       label=meta["label"], width=0.8)
                # Rolling avg overlay on bars
                if len(series) >= 5:
                    rolling = series.rolling(window=7, min_periods=3).mean()
                    ax.plot(df["date"], rolling, color=meta["color"], linewidth=2,
                            linestyle="--", alpha=0.7, label="7-day avg")
            else:
                ax.fill_between(df["date"], series, alpha=0.2, color=meta["color"])
                ax.plot(df["date"], series, color=meta["color"], linewidth=2,
                        marker="o", markersize=3, label=meta["label"])
                if len(series) >= 7:
                    rolling = series.rolling(window=7, min_periods=3).mean()
                    ax.plot(df["date"], rolling, color=meta["color"], linewidth=1.5,
                            linestyle="--", alpha=0.6, label="7-day avg")

            # Baseline reference line
            baseline = round(series[series > 0].mean(), 1) if (series > 0).any() else None
            if baseline:
                ax.axhline(y=baseline, color=meta["color"], linestyle=":", alpha=0.4, linewidth=1)
                ax.annotate(f"avg {baseline}", xy=(df["date"].iloc[-1], baseline),
                            xytext=(4, 4), textcoords="offset points", fontsize=7,
                            color=meta["color"], alpha=0.7)

            ax.set_ylabel(meta["label"], fontsize=9)
            ax.set_xlabel("Date", fontsize=9)
            ax.set_title(chart_title, fontsize=11, fontweight="bold", pad=8)
            ax.legend(fontsize=8)
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
            fig.autofmt_xdate()
            fig.tight_layout()

            path = _save_chart(fig, self.output_dir, f"trend_{metric}_{user_id}")
            return {
                "chart_type": "metric_trend",
                "metric": metric,
                "chart_path": path,
                "caption": chart_title,
                "points": len(df),
                "period_days": days,
                "generated_at": datetime.now().isoformat(),
            }
        except Exception as e:
            self.logger.error(f"Error generating metric trend for {user_id}/{metric}: {e}")
            return {"error": str(e)}

    # Running activity type keywords — used to filter activities for running-specific metrics
    _RUN_KEYWORDS = ("run", "trail", "track", "virtual_run", "treadmill")

    async def generate_weekly_bars(
        self,
        user_id: str,
        metric: str = "distance_km",
        weeks: int = 8,
    ) -> Dict[str, Any]:
        """Aggregate a daily metric by ISO week and draw bars + trend line.

        For running-specific metrics (distance_km, active_minutes when asked about runs),
        data is sourced from individual activity records so only running distance is counted.
        All other metrics use daily summaries.
        """
        try:
            days = weeks * 7
            end_date = datetime.now(timezone.utc)
            start_date = end_date - timedelta(days=days)

            use_activities = metric == "distance_km"

            if use_activities:
                # Source running distance from activity records, not daily summaries
                activities = await self.data_tools.db_tools.get_recent_activities(
                    user_id, limit=weeks * 7
                )
                runs = [
                    a for a in activities
                    if any(kw in (a.get("activity_type") or a.get("activity_name") or "").lower()
                           for kw in self._RUN_KEYWORDS)
                    and a.get("start_time") is not None
                    and a["start_time"] >= start_date
                ]
                if not runs:
                    return {"error": "No running activities found in this period"}

                records = []
                for a in runs:
                    st = a["start_time"]
                    if hasattr(st, "tzinfo") and st.tzinfo is not None:
                        st = st.astimezone(timezone.utc).replace(tzinfo=None)
                    records.append({"date": st, "distance_km": float(a.get("distance_km") or 0)})

                df = pd.DataFrame(records)
                df["date"] = pd.to_datetime(df["date"])
            else:
                summaries = await self.data_tools.db_tools.get_daily_summaries(user_id, start_date, end_date)
                if not summaries:
                    return {"error": "No summary data available"}
                df = pd.DataFrame(summaries)
                if df.empty or metric not in df.columns:
                    available = [k for k in _METRIC_META if k in df.columns]
                    return {"error": f"Metric '{metric}' not found. Available: {available}"}
                df["date"] = pd.to_datetime(df["date"], utc=True).dt.tz_convert(None)

            df = df.sort_values("date")
            df["week"] = df["date"].dt.to_period("W").apply(lambda r: r.start_time)
            weekly = df.groupby("week")[metric].sum().reset_index()
            weekly.columns = ["week", "value"]

            meta = _METRIC_META.get(metric, {"label": metric, "color": _PALETTE["teal"]})
            chart_title = f"Weekly {meta['label']} — last {weeks} weeks"

            fig, ax = plt.subplots(figsize=(12, 5))
            _apply_style(fig, [ax])

            bar_width = timedelta(days=5)
            ax.bar(weekly["week"], weekly["value"], width=bar_width, color=meta["color"],
                   alpha=0.75, label=meta["label"])

            # Trend line
            if len(weekly) >= 3:
                trend = weekly["value"].rolling(window=3, min_periods=1).mean()
                ax.plot(weekly["week"], trend, color=meta["color"], linewidth=2,
                        linestyle="-", alpha=0.85, label="3-week avg")

            ax.set_ylabel(meta["label"], fontsize=9)
            ax.set_xlabel("Week starting", fontsize=9)
            ax.set_title(chart_title, fontsize=11, fontweight="bold", pad=8)
            ax.legend(fontsize=8)
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
            fig.autofmt_xdate()
            fig.tight_layout()

            path = _save_chart(fig, self.output_dir, f"weekly_{metric}_{user_id}")
            return {
                "chart_type": "weekly_bars",
                "metric": metric,
                "chart_path": path,
                "caption": chart_title,
                "weeks": len(weekly),
                "generated_at": datetime.now().isoformat(),
            }
        except Exception as e:
            self.logger.error(f"Error generating weekly bars for {user_id}/{metric}: {e}")
            return {"error": str(e)}

    async def generate_activity_bars(
        self,
        user_id: str,
        metric: str = "distance_km",
        days: int = 14,
    ) -> Dict[str, Any]:
        """One bar per individual running activity — shows each run separately."""
        try:
            end_date = datetime.now(timezone.utc)
            start_date = end_date - timedelta(days=days)
            activities = await self.data_tools.db_tools.get_recent_activities(user_id, limit=days * 2)

            runs = [
                a for a in activities
                if any(kw in (a.get("activity_type") or a.get("activity_name") or "").lower()
                       for kw in self._RUN_KEYWORDS)
                and a.get("start_time") is not None
                and a["start_time"] >= start_date
            ]
            if not runs:
                return {"error": f"No running activities in the last {days} days"}

            runs_sorted = sorted(runs, key=lambda a: a["start_time"])

            labels, values = [], []
            for a in runs_sorted:
                st = a["start_time"]
                if hasattr(st, "tzinfo") and st.tzinfo:
                    st = st.astimezone(timezone.utc).replace(tzinfo=None)
                label = st.strftime("%b %d")
                if metric == "distance_km":
                    val = float(a.get("distance_km") or 0)
                elif metric == "duration_minutes":
                    val = round(float(a.get("duration_seconds") or 0) / 60, 1)
                else:
                    val = float(a.get(metric) or 0)
                labels.append(label)
                values.append(val)

            meta = _METRIC_META.get(metric, {"label": metric, "color": _PALETTE["teal"]})
            chart_title = f"Individual Runs — {meta['label']} — last {days} days"

            fig, ax = plt.subplots(figsize=(max(10, len(labels) * 0.9), 5))
            _apply_style(fig, [ax])

            x = range(len(labels))
            bars = ax.bar(x, values, color=meta["color"], alpha=0.8, label=meta["label"])

            # Value labels on top of bars
            for bar, val in zip(bars, values):
                if val > 0:
                    ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + max(values) * 0.01,
                            f"{val:.1f}", ha="center", va="bottom", fontsize=7.5)

            # Average line
            if values:
                avg = round(sum(values) / len(values), 1)
                ax.axhline(y=avg, color=meta["color"], linestyle="--", alpha=0.45, linewidth=1.5)
                ax.annotate(f"avg {avg}", xy=(len(labels) - 0.5, avg),
                            xytext=(4, 4), textcoords="offset points", fontsize=7,
                            color=meta["color"], alpha=0.8)

            ax.set_xticks(list(x))
            ax.set_xticklabels(labels, rotation=30, ha="right", fontsize=8)
            ax.set_ylabel(meta["label"], fontsize=9)
            ax.set_title(chart_title, fontsize=11, fontweight="bold", pad=8)
            ax.legend(fontsize=8)
            fig.tight_layout()

            path = _save_chart(fig, self.output_dir, f"activity_bars_{user_id}")
            return {
                "chart_type": "activity_bars",
                "metric": metric,
                "chart_path": path,
                "caption": chart_title,
                "runs": len(runs_sorted),
                "generated_at": datetime.now().isoformat(),
            }
        except Exception as e:
            self.logger.error(f"Error generating activity bars for {user_id}: {e}")
            return {"error": str(e)}

    async def generate_chart(self, user_id: str, chart_request: str) -> Dict[str, Any]:
        """
        Dispatch chart generation based on a spec string.

        Spec format (key=value, comma-separated):
            metric=<column>          – any column from daily summaries or "duration_minutes"
            chart_type=trend|bar|weekly|activity_bars|activity|dashboard
            days=<int>               – window in days (default: trend=14, activity_bars=14)
            weeks=<int>              – window for weekly bar charts (default 8)
            title=<string>           – optional custom title

        Chart type guide:
            trend          – line + area fill over days (good for continuous metrics like HR, VO2max)
            bar            – daily bars over days (good for discrete metrics: sleep, any daily value)
            weekly         – bars aggregated per ISO week (good for volume trends over weeks)
            activity_bars  – one bar per individual run (good for "show me each run")
            activity       – pace + HR by split for a single run
            dashboard      – 3-panel full overview (default when no metric given)

        Examples:
            "metric=sleep_duration_hours,days=14"          # daily sleep bars
            "metric=resting_heart_rate,chart_type=trend,days=30"
            "metric=distance_km,chart_type=bar,days=7"    # daily distance bars
            "metric=distance_km,chart_type=weekly,weeks=8"
            "chart_type=activity_bars,days=14"             # one bar per run, last 14 days
            "chart_type=activity"                          # last run splits
            "chart_type=dashboard"
        """
        spec = _parse_chart_spec(chart_request or "")
        chart_type = spec.get("chart_type", "")
        metric = spec.get("metric", "")

        # One bar per individual run activity
        if chart_type == "activity_bars":
            return await self.generate_activity_bars(
                user_id,
                metric=metric or "distance_km",
                days=int(spec.get("days", 14)),
            )

        # Single activity split chart
        if chart_type == "activity" or (chart_type == "" and "activity" in (chart_request or "").lower() and not metric):
            digits = "".join(ch for ch in (chart_request or "") if ch.isdigit())
            if digits:
                return await self.generate_running_activity_chart(user_id, digits)
            latest = await self.data_tools.fetch_latest_running_activity_details(user_id, 30)
            activity_id = latest.get("activity_id")
            if activity_id:
                return await self.generate_running_activity_chart(user_id, str(activity_id))
            return {"error": "No running activity found for chart generation"}

        # Weekly bar chart
        if chart_type == "weekly" or (metric and spec.get("weeks")):
            return await self.generate_weekly_bars(
                user_id,
                metric=metric or "distance_km",
                weeks=int(spec.get("weeks", 8)),
            )

        # Single-metric trend (bar override via spec or auto-detected for discrete metrics)
        if metric and metric != "dashboard":
            use_bars = chart_type == "bar" or metric in ChartTools._BAR_METRICS
            return await self.generate_metric_trend(
                user_id,
                metric=metric,
                days=int(spec.get("days", 14)),
                title=spec.get("title", ""),
                use_bars=use_bars,
            )

        # Default: full dashboard
        return await self.generate_multi_metric_dashboard(user_id, int(spec.get("days", 30)))


def get_chart_tools(data_tools: DataTools = None, config: Config = None) -> ChartTools:
    """Get or create chart tools instance."""
    if not hasattr(get_chart_tools, "_instance"):
        if not all([data_tools, config]):
            raise ValueError("data_tools and config are required for first initialization")
        get_chart_tools._instance = ChartTools(data_tools, config)
    return get_chart_tools._instance


def init_chart_tools(data_tools: DataTools, config: Config) -> ChartTools:
    """Initialize and return chart tools instance."""
    tools = ChartTools(data_tools, config)
    get_chart_tools._instance = tools
    return tools
