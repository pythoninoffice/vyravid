-- Vyravid local SQLite schema (Supabase-compatible subset)

CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT,
    first_name TEXT,
    last_name TEXT,
    phone_number TEXT,
    bio TEXT,
    avatar_url TEXT,
    avatar_character_id TEXT,
    watermark_logo_url TEXT,
    watermark_logo_gcs_path TEXT,
    stripe_customer_id TEXT,
    type TEXT DEFAULT 'local',
    has_watched_tutorial INTEGER DEFAULT 1,
    created_at TEXT,
    updated_at TEXT,
    email_confirmed_at TEXT
);

CREATE TABLE IF NOT EXISTS video_projects (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    title TEXT,
    status TEXT DEFAULT 'draft',
    created_at TEXT,
    completed_at TEXT,
    updated_at TEXT,
    duration REAL DEFAULT 0,
    file_size INTEGER DEFAULT 0,
    gcs_path TEXT,
    gcs_signed_url TEXT,
    gcs_signed_url_expires_at TEXT,
    thumbnail_url TEXT,
    processing_options TEXT,
    story_content TEXT,
    processing_method TEXT DEFAULT 'local',
    webhook_received_at TEXT,
    audio_file_id TEXT,
    draft_data TEXT,
    source_type TEXT DEFAULT 'text_processing',
    is_template INTEGER DEFAULT 0,
    template_name TEXT,
    project_tags TEXT,
    last_edited_at TEXT,
    edit_count INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_video_projects_user_id ON video_projects(user_id);
CREATE INDEX IF NOT EXISTS idx_video_projects_status ON video_projects(status);
CREATE INDEX IF NOT EXISTS idx_video_projects_created_at ON video_projects(created_at);

CREATE TABLE IF NOT EXISTS video_project_assets (
    id TEXT PRIMARY KEY,
    project_id TEXT,
    created_at TEXT,
    original_text_content TEXT,
    processed_text_content TEXT,
    text_source TEXT DEFAULT 'custom',
    original_story_id TEXT,
    user_edits TEXT,
    custom_instructions TEXT,
    output_language TEXT DEFAULT 'English',
    audio_file_id TEXT,
    audio_gcs_path TEXT,
    audio_signed_url TEXT,
    audio_signed_url_expires_at TEXT,
    voice_settings TEXT,
    audio_settings TEXT,
    audio_duration_seconds REAL,
    caption_file_path TEXT,
    caption_gcs_path TEXT,
    caption_settings TEXT,
    word_segments TEXT,
    background_music_id TEXT,
    music_settings TEXT
);

CREATE TABLE IF NOT EXISTS video_project_backgrounds (
    id TEXT PRIMARY KEY,
    project_id TEXT,
    created_at TEXT,
    background_type TEXT NOT NULL,
    sort_order INTEGER DEFAULT 0,
    video_url TEXT,
    video_gcs_path TEXT,
    video_local_path TEXT,
    video_duration_seconds REAL,
    image_url TEXT,
    image_gcs_path TEXT,
    image_local_path TEXT,
    image_width INTEGER,
    image_height INTEGER,
    image_id TEXT,
    start_time REAL DEFAULT 0,
    end_time REAL DEFAULT 0,
    transition_type TEXT DEFAULT 'cut',
    transition_duration REAL DEFAULT 0,
    camera_movement TEXT,
    greenscreen_effect TEXT,
    file_size INTEGER,
    file_format TEXT,
    is_user_uploaded INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_vpb_project_id ON video_project_backgrounds(project_id);

CREATE TABLE IF NOT EXISTS video_project_processing_settings (
    id TEXT PRIMARY KEY,
    project_id TEXT,
    created_at TEXT,
    resolution TEXT,
    aspect_ratio TEXT,
    fps INTEGER DEFAULT 30,
    video_codec TEXT DEFAULT 'libx264',
    audio_codec TEXT DEFAULT 'aac',
    quality_level TEXT DEFAULT 'medium',
    caption_position TEXT DEFAULT 'middle',
    font_family TEXT DEFAULT 'Luckiest Guy',
    font_size INTEGER DEFAULT 72,
    font_file_path TEXT,
    highlight_color TEXT DEFAULT '&H00FFFF&',
    default_color TEXT DEFAULT '&HFFFFFF&',
    subtitle_style TEXT DEFAULT 'karaoke',
    processing_method TEXT DEFAULT 'local',
    cloud_job_id TEXT,
    additional_options TEXT
);

CREATE TABLE IF NOT EXISTS video_project_edit_history (
    id TEXT PRIMARY KEY,
    project_id TEXT,
    user_id TEXT,
    edited_at TEXT,
    edit_type TEXT NOT NULL,
    field_changed TEXT,
    old_value TEXT,
    new_value TEXT,
    edit_description TEXT
);

CREATE TABLE IF NOT EXISTS video_project_languages (
    id TEXT PRIMARY KEY,
    project_id TEXT,
    language_code TEXT,
    language_name TEXT,
    is_primary INTEGER DEFAULT 0,
    audio_file_id TEXT,
    audio_gcs_path TEXT,
    audio_signed_url TEXT,
    story_content TEXT,
    script_content TEXT,
    translation_status TEXT,
    draft_data TEXT,
    caption_settings TEXT,
    voice_settings TEXT,
    word_segments TEXT,
    created_at TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS project_scenes (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    created_at TEXT,
    updated_at TEXT,
    scene_index INTEGER NOT NULL,
    description TEXT,
    prompt TEXT,
    scene_type TEXT,
    scene_script TEXT,
    layout_type TEXT,
    target_duration REAL,
    start_time REAL,
    end_time REAL,
    character_ids TEXT,
    dialogue_turns TEXT,
    character_layout TEXT,
    generated_image TEXT,
    animation_prompt TEXT,
    animated_video TEXT,
    camera_movement TEXT,
    transition_type TEXT,
    transition_duration REAL,
    greenscreen_effect TEXT,
    scene_audio TEXT
);

CREATE INDEX IF NOT EXISTS idx_project_scenes_project_id ON project_scenes(project_id);

CREATE TABLE IF NOT EXISTS project_text_layers (
    id TEXT PRIMARY KEY,
    project_id TEXT,
    created_at TEXT,
    updated_at TEXT,
    layer_data TEXT
);

CREATE TABLE IF NOT EXISTS generated_images (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    prompt TEXT,
    model_name TEXT,
    provider TEXT DEFAULT 'replicate',
    provider_prediction_id TEXT,
    status TEXT DEFAULT 'pending',
    gcs_path TEXT,
    gcs_signed_url TEXT,
    thumbnail_gcs_path TEXT,
    thumbnail_signed_url TEXT,
    width INTEGER,
    height INTEGER,
    num_outputs INTEGER DEFAULT 1,
    file_size INTEGER,
    generation_time_ms INTEGER,
    error_message TEXT,
    folder_id TEXT,
    tags TEXT,
    media_type TEXT DEFAULT 'image',
    aspect_ratio TEXT,
    reference_image_ids TEXT,
    metadata TEXT,
    created_at TEXT,
    updated_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_generated_images_user_id ON generated_images(user_id);

CREATE TABLE IF NOT EXISTS image_folders (
    id TEXT PRIMARY KEY,
    user_id TEXT,
    name TEXT,
    parent_id TEXT,
    created_at TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS character_designs (
    id TEXT PRIMARY KEY,
    user_id TEXT,
    name TEXT,
    description TEXT,
    style TEXT,
    base_prompt TEXT,
    primary_image_id TEXT,
    tags TEXT,
    visual_style_notes TEXT,
    collection_id TEXT,
    metadata TEXT,
    created_at TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS character_collections (
    id TEXT PRIMARY KEY,
    user_id TEXT,
    name TEXT,
    description TEXT,
    created_at TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS character_reference_images (
    id TEXT PRIMARY KEY,
    character_id TEXT,
    image_id TEXT,
    sort_order INTEGER DEFAULT 0,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS custom_voices (
    id TEXT PRIMARY KEY,
    user_id TEXT,
    name TEXT,
    provider TEXT,
    provider_voice_id TEXT,
    sample_gcs_path TEXT,
    sample_url TEXT,
    metadata TEXT,
    created_at TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS user_images (
    id TEXT PRIMARY KEY,
    user_id TEXT,
    gcs_path TEXT,
    gcs_signed_url TEXT,
    thumbnail_path TEXT,
    thumbnail_url TEXT,
    original_filename TEXT,
    width INTEGER,
    height INTEGER,
    file_size INTEGER,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS audio_files (
    id TEXT PRIMARY KEY,
    user_id TEXT,
    project_id TEXT,
    gcs_path TEXT,
    gcs_signed_url TEXT,
    file_path TEXT,
    duration REAL,
    status TEXT DEFAULT 'completed',
    voice_id TEXT,
    tts_provider TEXT,
    language_code TEXT DEFAULT 'en',
    text_content TEXT,
    metadata TEXT,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS music_tracks (
    id TEXT PRIMARY KEY,
    name TEXT,
    gcs_path TEXT,
    url TEXT,
    duration REAL,
    genre TEXT,
    is_preset INTEGER DEFAULT 1,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS background_tasks (
    id TEXT PRIMARY KEY,
    user_id TEXT,
    task_type TEXT,
    status TEXT DEFAULT 'pending',
    progress REAL DEFAULT 0,
    result TEXT,
    error_message TEXT,
    created_at TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS kv_store (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated_at TEXT
);
