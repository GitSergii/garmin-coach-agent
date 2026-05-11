-- AI GarminCoach Database Schema - MVP Version
-- PostgreSQL Database Schema for Core Functionality
-- Version: 1.0 MVP

-- =============================================================================
-- CORE TABLES FOR MVP
-- =============================================================================

-- Users table for system authentication and basic info
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    telegram_user_id BIGINT UNIQUE NOT NULL,
    telegram_username VARCHAR(100),
    telegram_first_name VARCHAR(100),
    telegram_last_name VARCHAR(100),
    
    -- Garmin Connect credentials (encrypted)
    garmin_username VARCHAR(255),
    garmin_password_encrypted TEXT, -- Encrypted storage
    garmin_session_token_encrypted TEXT, -- Encrypted session token
    garmin_last_sync TIMESTAMP WITH TIME ZONE,
    
    -- User preferences
    timezone VARCHAR(50) DEFAULT 'UTC',
    language_code VARCHAR(10) DEFAULT 'en',
    
    -- Privacy and consent
    data_sharing_consent BOOLEAN DEFAULT false,
    analytics_consent BOOLEAN DEFAULT false,
    
    -- System fields
    is_active BOOLEAN DEFAULT true,
    is_premium BOOLEAN DEFAULT false,
    last_activity TIMESTAMP WITH TIME ZONE,
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- User settings for personalization
CREATE TABLE user_settings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    
    -- Coaching preferences
    coaching_style VARCHAR(50) DEFAULT 'balanced', -- motivational, analytical, balanced
    preferred_metrics TEXT[] DEFAULT ARRAY['steps', 'heart_rate', 'sleep'],
    reminder_frequency VARCHAR(20) DEFAULT 'daily',
    
    -- Notification settings
    enable_daily_summary BOOLEAN DEFAULT true,
    enable_goal_reminders BOOLEAN DEFAULT true,
    enable_achievement_alerts BOOLEAN DEFAULT true,
    enable_health_insights BOOLEAN DEFAULT true,
    
    -- Display preferences
    use_metric_units BOOLEAN DEFAULT true,
    chart_style VARCHAR(20) DEFAULT 'modern',
    
    -- Advanced settings
    data_sync_frequency VARCHAR(20) DEFAULT 'daily',
    max_chart_history_days INTEGER DEFAULT 30,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(user_id)
);

-- User goals for fitness tracking
CREATE TABLE user_goals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    
    -- Goal details
    goal_type VARCHAR(50) NOT NULL, -- steps, distance, weight, heart_rate, sleep
    goal_name VARCHAR(200) NOT NULL,
    target_value DECIMAL(10,2) NOT NULL,
    current_value DECIMAL(10,2) DEFAULT 0.0,
    unit VARCHAR(20) NOT NULL,
    
    -- Timeline
    target_date TIMESTAMP WITH TIME ZONE,
    start_date TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    achieved_date TIMESTAMP WITH TIME ZONE,
    
    -- Status
    status VARCHAR(20) DEFAULT 'active', -- active, completed, paused, cancelled
    priority VARCHAR(20) DEFAULT 'medium', -- low, medium, high
    
    -- Progress tracking
    progress_percentage DECIMAL(5,2) DEFAULT 0.0,
    best_streak_days INTEGER DEFAULT 0,
    current_streak_days INTEGER DEFAULT 0,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Conversation sessions for context management
CREATE TABLE conversation_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    
    -- Session details
    session_start TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    session_end TIMESTAMP WITH TIME ZONE,
    is_active BOOLEAN DEFAULT true,
    
    -- AI context
    conversation_summary TEXT,
    primary_topics TEXT[],
    user_intent VARCHAR(100),
    
    -- Metrics
    total_messages INTEGER DEFAULT 0,
    total_ai_responses INTEGER DEFAULT 0,
    avg_response_time_ms DECIMAL(8,2),
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Individual messages for conversation history
CREATE TABLE conversation_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES conversation_sessions(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    
    -- Message content
    message_type VARCHAR(20) NOT NULL, -- user_message, ai_response, system_message
    message_text TEXT NOT NULL,
    message_intent VARCHAR(100),
    
    -- AI response metadata
    ai_model_used VARCHAR(50),
    response_time_ms DECIMAL(8,2),
    confidence_score DECIMAL(3,2),
    tokens_used INTEGER,
    
    -- Features used
    tools_used TEXT[],
    charts_generated BOOLEAN DEFAULT false,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Daily activity summaries from Garmin
CREATE TABLE garmin_daily_summaries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    activity_date DATE NOT NULL,
    
    -- Basic metrics
    steps INTEGER,
    calories_burned DECIMAL(8,2),
    active_minutes INTEGER,
    distance_km DECIMAL(10,2),
    
    -- Sleep metrics
    sleep_duration_hours DECIMAL(4,2),
    sleep_quality_score DECIMAL(5,2),
    deep_sleep_minutes INTEGER,
    rem_sleep_minutes INTEGER,
    
    -- Heart rate metrics
    resting_heart_rate INTEGER,
    avg_heart_rate INTEGER,
    max_heart_rate INTEGER,
    
    -- Advanced metrics
    stress_level_avg DECIMAL(5,2),
    body_battery_level INTEGER,
    vo2_max DECIMAL(5,2),
    
    -- Data completeness
    data_completeness_percentage DECIMAL(5,2) DEFAULT 0.0,
    sync_status VARCHAR(20) DEFAULT 'pending',
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(user_id, activity_date)
);

-- Heart rate data (simplified for MVP)
CREATE TABLE garmin_heart_rate (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    recorded_at TIMESTAMP WITH TIME ZONE NOT NULL,
    
    heart_rate_bpm INTEGER NOT NULL,
    resting_heart_rate_bpm INTEGER,
    max_heart_rate_bpm INTEGER,
    activity_type VARCHAR(50),
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Sleep data
CREATE TABLE garmin_sleep (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    sleep_date DATE NOT NULL,
    
    -- Sleep timing
    bedtime TIMESTAMP WITH TIME ZONE,
    wake_time TIMESTAMP WITH TIME ZONE,
    
    -- Sleep duration (minutes)
    total_sleep_minutes INTEGER,
    deep_sleep_minutes INTEGER,
    light_sleep_minutes INTEGER,
    rem_sleep_minutes INTEGER,
    awake_minutes INTEGER,
    
    -- Sleep quality metrics
    sleep_score INTEGER, -- 0-100
    sleep_efficiency DECIMAL(5,2),
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(user_id, sleep_date)
);

-- Activities/workouts
CREATE TABLE garmin_activities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    garmin_activity_id BIGINT UNIQUE,
    
    -- Activity details
    activity_name VARCHAR(200),
    activity_type VARCHAR(100),
    start_time TIMESTAMP WITH TIME ZONE,
    duration_seconds INTEGER,
    
    -- Metrics
    distance_meters DECIMAL(10,2),
    calories_burned DECIMAL(8,2),
    avg_heart_rate INTEGER,
    max_heart_rate INTEGER,
    avg_speed_mps DECIMAL(8,4),
    max_speed_mps DECIMAL(8,4),
    
    -- Additional data
    elevation_gain_meters DECIMAL(8,2),
    avg_cadence DECIMAL(6,2),
    max_cadence DECIMAL(6,2),
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- AI response cache for cost optimization
CREATE TABLE ai_response_cache (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    
    -- Cache key components
    query_type VARCHAR(100) NOT NULL,
    query_hash VARCHAR(64) NOT NULL,
    date_range_start TIMESTAMP WITH TIME ZONE,
    date_range_end TIMESTAMP WITH TIME ZONE,
    
    -- Cached response
    response_text TEXT NOT NULL,
    chart_data JSONB,
    confidence_score DECIMAL(3,2),
    
    -- Cache metadata
    cache_hits INTEGER DEFAULT 0,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Generated charts metadata
CREATE TABLE generated_charts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    
    -- Chart details
    chart_type VARCHAR(50) NOT NULL,
    chart_title VARCHAR(200),
    data_source VARCHAR(100),
    date_range_start TIMESTAMP WITH TIME ZONE,
    date_range_end TIMESTAMP WITH TIME ZONE,
    
    -- Storage
    file_path VARCHAR(500),
    telegram_file_id VARCHAR(200),
    chart_config JSONB,
    
    -- Metadata
    generation_time_ms DECIMAL(8,2),
    file_size_bytes INTEGER,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP WITH TIME ZONE
);

-- API usage logging for cost tracking
CREATE TABLE api_usage_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    
    -- API call details
    api_service VARCHAR(50) NOT NULL, -- google_genai, garmin_connect, telegram
    feature_used VARCHAR(100) NOT NULL,
    response_time_ms DECIMAL(8,2) NOT NULL,
    
    -- Cost tracking
    tokens_used INTEGER,
    estimated_cost_usd DECIMAL(10,4),
    
    -- Performance metrics
    success BOOLEAN DEFAULT true,
    error_message TEXT,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- =============================================================================
-- INDEXES FOR PERFORMANCE
-- =============================================================================

-- User indexes
CREATE INDEX idx_users_telegram_user_id ON users(telegram_user_id);
CREATE INDEX idx_users_last_sync ON users(garmin_last_sync);

-- Conversation indexes
CREATE INDEX idx_conv_sessions_user_active ON conversation_sessions(user_id, is_active);
CREATE INDEX idx_conv_messages_session_time ON conversation_messages(session_id, created_at);
CREATE INDEX idx_conv_messages_user_time ON conversation_messages(user_id, created_at);

-- Garmin data indexes
CREATE INDEX idx_daily_summaries_user_date ON garmin_daily_summaries(user_id, activity_date DESC);
CREATE INDEX idx_heart_rate_user_time ON garmin_heart_rate(user_id, recorded_at);
CREATE INDEX idx_sleep_user_date ON garmin_sleep(user_id, sleep_date DESC);
CREATE INDEX idx_activities_user_recent ON garmin_activities(user_id, start_time DESC);

-- User goals indexes
CREATE INDEX idx_user_goals_user_active ON user_goals(user_id, status);

-- Cache indexes
CREATE INDEX idx_ai_cache_user_query ON ai_response_cache(user_id, query_type, query_hash);
CREATE INDEX idx_ai_cache_expires ON ai_response_cache(expires_at);

-- API usage indexes
CREATE INDEX idx_api_usage_service_time ON api_usage_log(api_service, created_at);
CREATE INDEX idx_api_usage_cost ON api_usage_log(estimated_cost_usd);

-- =============================================================================
-- FUNCTIONS AND TRIGGERS
-- =============================================================================

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Triggers for updated_at
CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON users FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_user_settings_updated_at BEFORE UPDATE ON user_settings FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_user_goals_updated_at BEFORE UPDATE ON user_goals FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_daily_summaries_updated_at BEFORE UPDATE ON garmin_daily_summaries FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_sleep_updated_at BEFORE UPDATE ON garmin_sleep FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_activities_updated_at BEFORE UPDATE ON garmin_activities FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_conversation_sessions_updated_at BEFORE UPDATE ON conversation_sessions FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- =============================================================================
-- INITIAL DATA AND COMPLETION
-- =============================================================================

-- Log successful schema deployment
DO $$
BEGIN
    RAISE NOTICE 'AI GarminCoach Database Schema Deployed Successfully';
    RAISE NOTICE 'Tables created: users, user_settings, user_goals, conversation_sessions, conversation_messages';
    RAISE NOTICE 'Garmin tables: garmin_daily_summaries, garmin_heart_rate, garmin_sleep, garmin_activities';
    RAISE NOTICE 'System tables: ai_response_cache, generated_charts, api_usage_log';
    RAISE NOTICE 'Database ready for application use';
END $$; 