from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, SecretStr, model_validator,AliasChoices
from pathlib import Path

class Settings(BaseSettings):
    gmail_user: str = ''
    gmail_app_password: SecretStr = SecretStr('')
    imap_host: str = 'imap.gmail.com'
    imap_port: int = 993
    smtp_host: str = 'smtp.gmail.com'
    smtp_port: int = 587
    supplier_mail_folder: str = 'TEST'
    supplier_mail_owner_id: str = ''
    supplier_mail_poll_seconds: int = Field(default=30, ge=10, le=3600)
    supplier_mail_state_file: str = str(Path(__file__).resolve().parents[3]/'runtime/supplier-mail.sqlite3')
    model_config = SettingsConfigDict(env_file=str(Path(__file__).resolve().parents[3]/'.env'), extra='ignore')
    database_url: str = 'postgresql://agent:invalid@127.0.0.1:55432/agent_sage'
    ai_provider: str = 'ollama'
    conversation_analysis_enabled: bool = True
    conversation_tool_calling_enabled: bool = True
    conversation_deepseek_primary_enabled: bool = False
    conversation_local_tool_calling_enabled: bool = False
    conversation_analysis_cloud_timeout: float = Field(default=12,ge=1,le=60)
    conversation_analysis_local_timeout: float = Field(default=30,ge=1,le=120)
    ai_fallback_provider: str = 'ollama'
    deepseek_api_key: SecretStr = SecretStr('')
    deepseek_base_url: str = 'https://api.deepseek.com'
    deepseek_model: str = 'deepseek-chat'
    deepseek_timeout_seconds: float = Field(default=60,ge=1,le=120)
    ai_daily_budget_usd: float = Field(default=1,ge=0,le=1000)
    ai_max_output_tokens: int = Field(default=1000,ge=128,le=4000)
    ollama_url: str = Field(default='http://127.0.0.1:11434',validation_alias=AliasChoices('OLLAMA_URL','OLLAMA_BASE_URL','ollama_url'))
    ollama_model: str = 'qwen2.5:7b'
    learning_enabled: bool = True
    sage_mcp_enabled: bool = False
    sage_article_sql_enabled: bool = False
    sage_modification_enabled: bool = False
    sage_mcp_timeout: float = Field(default=30,ge=3,le=45)
    learning_scheduler_enabled: bool = True
    learning_improvement_interval_seconds: int = Field(default=300,ge=30,le=86400)
    learning_improvement_min_conversations: int = Field(default=2,ge=2,le=1000)
    learning_dataset_directory: str = str(Path(__file__).resolve().parents[3]/'TEST/learning-data')
    ai_timeout: float = 180
    business_schema: str = 'sage_ai'
    business_ai_attempts: int = Field(default=2,ge=1,le=3)
    business_ai_timeout: float = Field(default=180,ge=5,le=600)
    chat_analysis_timeout: float = Field(default=240,ge=10,le=900)
    supplier_ai_timeout: float = Field(default=25,ge=5,le=60)
    approval_token: SecretStr = SecretStr('')
    allow_synthetic_references: bool = False
    business_rules_file: str = str(Path(__file__).with_name('business-rules.json'))
    sage_soap_base_url: str = 'http://192.168.9.200:8124'
    sage_soap_username: SecretStr = SecretStr('')
    sage_soap_password: SecretStr = SecretStr('')
    sage_soap_credential_file: str = ''
    sage_soap_dpapi_username: str = Field(default='AIAGT', pattern=r'^(AIAGT|admin)$')
    sage_soap_pool: str = 'POOL_AI_TEST'
    sage_soap_publication: str = 'WS_ARTICLE'
    sage_soap_language: str = 'FRA'
    sage_soap_timeout: float = Field(default=20,ge=1,le=60)
    sage_writes_enabled: bool = False
    sage_powershell_chat_enabled: bool = False
    sage_supplier_sql_connection_string: SecretStr = SecretStr('Data Source=tcp:sage,1433;Initial Catalog=x3v12;Encrypt=True;TrustServerCertificate=True;Connect Timeout=5')
    sage_supplier_sql_credential_file: str = str(Path(__file__).resolve().parents[3]/'runtime/sql-reader-credential.clixml')
    sage_supplier_ob_trust_server_certificate: bool = False
    sage_security_policy_file: str = ''
    sage_soap_ca_bundle: str = ''
    sage_soap_crl_bundle: str = ''
    pki_publication_enabled: bool = False
    pki_publication_directory: str = str(Path(__file__).resolve().parents[3]/'certs/approved-production/public-distribution')

    @model_validator(mode='after')
    def protected_soap_credentials(self):
        if self.sage_soap_credential_file:
            from app.core.dpapi_credential import load_aiagt_credential
            # Never fall back to an old administrator or plaintext password.
            self.sage_soap_username=SecretStr(self.sage_soap_dpapi_username)
            self.sage_soap_password=SecretStr('')
            if Path(self.sage_soap_credential_file).is_file():
                self.sage_soap_password=load_aiagt_credential(self.sage_soap_credential_file,self.sage_soap_dpapi_username)
        return self

settings = Settings()
