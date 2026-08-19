import os
from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    _project_env_file = Path(
        os.getenv("APP_ENV_FILE", Path(__file__).resolve().parents[1] / ".env")
    )
    model_config = SettingsConfigDict(env_file=_project_env_file, extra="ignore")

    app_env: str = "development"
    app_timezone: str = "Asia/Shanghai"
    app_tenant_id: str = Field(default="default", min_length=1, max_length=100)
    database_url: str = "postgresql+psycopg://localhost/performance_reports"
    database_connect_timeout_seconds: int = Field(default=3, ge=1, le=30)
    data_source: str = "local_csv"
    local_csv_path: str = "./data/sample_operations.csv"
    tencent_doc_url: str = ""
    tencent_doc_sheet_id: str = ""
    tencent_doc_timeout_seconds: int = Field(default=10, ge=1, le=30)
    tencent_sync_interval_seconds: int = Field(default=60, ge=10, le=3600)
    aily_action_api_key: str = ""
    business_api_key: str = ""
    platform_admin_api_key: str = ""
    platform_permission_mode: str = "open"
    platform_scheduler_enabled: bool = True
    platform_scheduler_poll_seconds: int = Field(default=20, ge=10, le=300)
    model_base_url: str = ""
    model_api_key: str = ""
    model_name: str = ""
    model_enabled: bool = False
    model_timeout_seconds: int = Field(default=60, ge=5, le=300)
    model_retry_max_attempts: int = Field(default=2, ge=1, le=5)
    model_prompt_token_budget: int = Field(default=6000, ge=500, le=100000)
    model_completion_token_budget: int = Field(default=1000, ge=100, le=16000)
    wecom_agent_mode: str = "cherry_local"
    cherry_agent_api_url: str = "http://127.0.0.1:24333"
    cherry_agent_api_key: str = ""
    cherry_agent_id: str = ""
    painting_cherry_agent_id: str = ""
    cherry_agent_timeout_seconds: int = Field(default=120, ge=10, le=600)
    cherry_agent_default_session_id: str = ""
    hermes_agent_url: str = ""
    hermes_agent_api_key: str = ""
    hermes_agent_timeout_seconds: int = Field(default=60, ge=5, le=300)
    conversation_lease_seconds: int = Field(default=120, ge=30, le=900)
    conversation_lease_monitor_enabled: bool = True
    conversation_lease_monitor_interval_seconds: int = Field(default=60, ge=10, le=3600)
    conversation_lease_alert_cooldown_seconds: int = Field(default=900, ge=60, le=86400)
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    deepseek_model: str = "deepseek-chat"
    deepseek_timeout_seconds: int = Field(default=15, ge=5, le=60)
    wecom_corp_id: str = ""
    wecom_corp_secret: str = ""
    wecom_agent_id: str = ""
    wecom_callback_token: str = ""
    wecom_encoding_aes_key: str = ""
    wecom_connection_api_key: str = ""
    wecom_api_base_url: str = "https://qyapi.weixin.qq.com"
    wecom_timeout_seconds: int = Field(default=10, ge=1, le=60)
    wecom_realtime_department_auth_enabled: bool = True
    wecom_aibot_bot_id: str = ""
    wecom_aibot_secret: str = ""
    wecom_aibot_ws_url: str = "wss://openws.work.weixin.qq.com"
    wecom_aibot_enabled: bool = True
    grinding_wecom_aibot_bot_id: str = ""
    grinding_wecom_aibot_secret: str = ""
    grinding_wecom_aibot_ws_url: str = "wss://openws.work.weixin.qq.com"
    grinding_wecom_aibot_enabled: bool = False
    welding_wecom_aibot_bot_id: str = ""
    welding_wecom_aibot_secret: str = ""
    welding_wecom_aibot_ws_url: str = "wss://openws.work.weixin.qq.com"
    welding_wecom_aibot_enabled: bool = False
    engraving_wecom_aibot_bot_id: str = ""
    engraving_wecom_aibot_secret: str = ""
    engraving_wecom_aibot_ws_url: str = "wss://openws.work.weixin.qq.com"
    engraving_wecom_aibot_enabled: bool = False
    painting_wecom_aibot_bot_id: str = ""
    painting_wecom_aibot_secret: str = ""
    painting_wecom_aibot_ws_url: str = "wss://openws.work.weixin.qq.com"
    painting_wecom_aibot_enabled: bool = False
    app_base_url: str = "http://127.0.0.1:8002"
    report_files_dir: str = "./data/generated_reports"
    report_renderer_command: str = "node"
    workshop_report_renderer_script: str = "./scripts/render_report_png.mjs"
    workshop_report_output_dir: str = "./data/generated_reports/workshop"
    workshop_report_image_width: int = Field(default=1200, ge=800, le=2400)
    workshop_report_image_timeout_seconds: int = Field(default=30, ge=5, le=120)
    workshop_data_adapter: str = "mock"
    jiandaoyun_mcp_url: str = ""
    jiandaoyun_mcp_timeout_seconds: int = Field(default=30, ge=5, le=120)
    jiandaoyun_max_concurrency: int = Field(default=3, ge=1, le=20)
    jiandaoyun_requests_per_second: float = Field(default=2.0, ge=0.1, le=50)
    jiandaoyun_retry_max_attempts: int = Field(default=4, ge=1, le=10)
    jiandaoyun_singleflight_enabled: bool = True
    jiandaoyun_workshop_app_id: str = "659d2050806aac7d76af53f5"
    jiandaoyun_workshop_entry_id: str = "68301da48ef10ecd50d643b7"
    workshop_mock_data_path: str = "./data/workshop_process_records_mock.json"
    workshop_work_report_mock_data_path: str = "./data/workshop_work_reports_mock.json"
    workshop_work_report_adapter: str = "mock"
    jiandaoyun_work_report_entry_id: str = ""
    jiandaoyun_work_report_field_map: str = "{}"
    jiandaoyun_welding_pick_work_report_entry_id: str = ""
    jiandaoyun_welding_pick_work_report_field_map: str = "{}"
    workshop_report_department: str = "焊接部"
    workshop_department_access_map: str = "{}"
    workshop_realtime_query_enabled: bool = True
    workshop_excel_max_concurrency: int = Field(default=3, ge=1, le=20)
    workshop_png_max_concurrency: int = Field(default=1, ge=1, le=10)
    workshop_card_item_limit: int = Field(default=5, ge=1, le=20)
    workshop_allow_mock_in_production: bool = False
    workshop_report_max_image_rows: int = Field(default=100, ge=10, le=500)
    workshop_report_schedule_enabled: bool = False
    workshop_scheduled_report_enabled: bool = False
    workshop_scheduled_report_time: str = "08:30"
    workshop_scheduled_report_targets: str = "{}"
    workshop_scheduled_report_state_dir: str = "./data/scheduled_reports_state"
    workshop_scheduled_report_include_order: bool = True
    workshop_scheduled_report_include_work: bool = True
    rag_embedding_model: str = "BAAI/bge-small-zh-v1.5"
    rag_model_cache_dir: str = "./data/models/fastembed"
    rag_chunk_size: int = Field(default=450, ge=100, le=4000)
    rag_chunk_overlap: int = Field(default=80, ge=0, le=1000)
    rag_minimum_score: float = Field(default=0.35, ge=0, le=1)
    rag_max_upload_bytes: int = Field(default=10_485_760, ge=1024, le=104_857_600)
    rag_enabled: bool = False
    mcp_knowledge_tools_enabled: bool = True
    # Set by a department-specific MCP executable. Empty scope exposes no
    # department tools so a shared, unscoped MCP process cannot leak data.
    mcp_department_scope: str = ""

    @field_validator("jiandaoyun_mcp_url", mode="before")
    @classmethod
    def normalize_jiandaoyun_mcp_url(cls, value):
        if not isinstance(value, str):
            return value
        marker = "https://mcp.jiandaoyun.com/mcp/"
        position = value.rfind(marker)
        return value[position:].strip() if position >= 0 else value.strip()

@lru_cache
def get_settings() -> Settings:
    return Settings()
