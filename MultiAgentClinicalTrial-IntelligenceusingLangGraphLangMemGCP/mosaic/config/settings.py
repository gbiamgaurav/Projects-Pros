
# Single source file for all the configuration 

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field 


class Settings(BaseSettings):
    """_summary_

    Args:
        BaseSettings (_type_): _description_
    """
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",

    )

openai_api_key: str = Field(
    ...,
    description="Open AI API key for LLM and Embeddings"
)

openai_embedding_model: str = Field(
    default="text-embedding-3-large",
    description="OpenAI model used to generate the vector embeddings"
)

openai_chat_model: str = Field(
    default="gpt-4o",
    description="OpenAI model used for agent reasoning",
)

langsmith_api_key: str = Field(
    ...,
    description="LangSmith API Key for agent tracing"
)

langsmith_project: str = Field(
    default="clinical_trial_intelligence",
    description="LangSmith project name"

)

langsmith_tracing_v2: bool = Field(
    default=True,
    description="Enable langsmith tracing for all the agent runs"
)

gcp_project_id: str = Field(
    ...,
    description="GCP Project ID",
)

gcp_region: str = Field(
    default="us-central1",
    description="GCP region for all the cloud resources"
)

gcs_bucket_name: str = Field(
    ...,
    description="Google Cloud storage bucket name"
)

db_host: str = Field(
    ...,
    description="Cloud SQL host IP (local) or socket path (Cloud Run)"
)

db_port: str = Field(
    default=5432,
    description="PostgreSQL port"
)

db_name: str = Field(
    default="clinical_trial_db",
    description="PostgreSQL database name"
)

db_user: str = Field(
    ...,
    description="PostgreSQL database user"
)

db_password: str = Field(
    ...,
    description="PostgreSQL database password"
)


clinical_trials_base_url: str = Field(
    default="https://clinicaltrials.gov/api/v2",
    description="ClinicalTrials.govAPI V2 base url"
)

clinical_trial_page_size: int = Field(
    default=100,
    description="Number of studies to fetch per API page"
)

pubmed_base_url: str = Field(
    default="https://eutils.ncbi.nlm.nih.giv/entrez/eutils",
    description="Pubmed eutils API base url",
)

api_host: str = Field(
    default="0.0.0.0",
    description="FAST API Host Address",
)

api_port: int = Field(
    default=8000,
    description="FAST API Port",
)

api_env: str = Field(
    default="development",
    description="Environment name: development or production",
)

@property
def database_url(self) -> str:
    """_summary_
    Builds the full async postgreSQL connection string from parts
    we use asyncpg as the async postgresql driver
    Returns:
        str: _description_
    """
    return (
        f"postgresql+asyncpg://"
        f"{self.db_user}:{self.db_password}"
        f"{self.db_host}:{self.db_port}"
        f"/{self.db_name}"
    )

@property
def is_production(self) -> bool:
    """_summary_

    Returns:
        bool: _description_
    """
    return self.api_env.lower() == "production"


# Singleton instance
settings = Settings()

