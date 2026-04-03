"""
Unit tests for Docker Compose configuration validation.

Validates: Requirements 1.1–1.12, 5.1–5.6, 6.1, 6.3
"""

import json
import os

import pytest
import yaml

COMPOSE_FILE = os.path.join(
    os.path.dirname(__file__), "..", "docker-compose.medical.yaml"
)


@pytest.fixture(scope="module")
def compose():
    with open(COMPOSE_FILE) as f:
        return yaml.safe_load(f)


@pytest.fixture(scope="module")
def service(compose):
    return compose["services"]["open-webui"]


@pytest.fixture(scope="module")
def env_vars(service):
    """Parse the environment list into a dict."""
    env = {}
    for item in service["environment"]:
        key, _, value = item.partition("=")
        env[key] = value
    return env


# --- Requirement 1.1: Image ---


def test_image(service):
    """Req 1.1: Service uses the correct Open WebUI image."""
    assert service["image"] == "ghcr.io/open-webui/open-webui:main"


# --- Requirement 1.12: Port mapping ---


def test_port_mapping(service):
    """Req 1.12: Host port 3000 maps to container port 8080."""
    assert "3000:8080" in service["ports"]


# --- Requirement 1.1: Persistent volume ---


def test_volume_mount(service):
    """Req 1.1: Persistent volume open-webui mounted at /app/backend/data."""
    assert "open-webui:/app/backend/data" in service["volumes"]


def test_volume_defined(compose):
    """Req 1.1: Top-level volume 'open-webui' is defined."""
    assert "open-webui" in compose["volumes"]


# --- Requirement 1.2: OpenAI API connection ---


def test_openai_api_base_url(env_vars):
    """Req 1.2: OPENAI_API_BASE_URL points to OpenAI."""
    assert env_vars["OPENAI_API_BASE_URL"] == "https://api.openai.com/v1"


def test_openai_api_key(env_vars):
    """Req 1.2: OPENAI_API_KEY references host env variable."""
    assert env_vars["OPENAI_API_KEY"] == "${OPENAI_API_KEY}"


# --- Requirement 1.3 / 5.6: Ollama disabled ---


def test_ollama_disabled(env_vars):
    """Req 1.3, 5.6: ENABLE_OLLAMA_API is false."""
    assert env_vars["ENABLE_OLLAMA_API"] == "false"


# --- Requirement 1.4: WEBUI_NAME ---


def test_webui_name(env_vars):
    """Req 1.4: WEBUI_NAME is 'Rome Medical Assistant'."""
    assert env_vars["WEBUI_NAME"] == "Rome Medical Assistant"


# --- Requirement 1.5 / 5.5: DEFAULT_MODELS ---


def test_default_models(env_vars):
    """Req 1.5, 5.5: DEFAULT_MODELS is gpt-5.4."""
    assert env_vars["DEFAULT_MODELS"] == "gpt-5.4"


# --- Requirement 1.6 / 5.1: Image generation disabled ---


def test_image_generation_disabled(env_vars):
    """Req 1.6, 5.1: ENABLE_IMAGE_GENERATION is false."""
    assert env_vars["ENABLE_IMAGE_GENERATION"] == "false"


# --- Requirement 1.7 / 5.3: Community sharing disabled ---


def test_community_sharing_disabled(env_vars):
    """Req 1.7, 5.3: ENABLE_COMMUNITY_SHARING is false."""
    assert env_vars["ENABLE_COMMUNITY_SHARING"] == "false"


# --- Requirement 1.8 / 5.2: Web search disabled ---


def test_web_search_disabled(env_vars):
    """Req 1.8, 5.2: ENABLE_WEB_SEARCH is false."""
    assert env_vars["ENABLE_WEB_SEARCH"] == "false"


# --- Requirement 1.9 / 5.4: Code interpreter disabled ---


def test_code_interpreter_disabled(env_vars):
    """Req 1.9, 5.4: ENABLE_CODE_INTERPRETER is false."""
    assert env_vars["ENABLE_CODE_INTERPRETER"] == "false"


# --- Requirement 1.11: Authentication ---


def test_webui_auth(env_vars):
    """Req 1.11: WEBUI_AUTH is true."""
    assert env_vars["WEBUI_AUTH"] == "true"


# --- Requirement 1.10, 6.1, 6.3: WEBUI_BANNERS ---


@pytest.fixture(scope="module")
def banners(env_vars):
    """Parse the WEBUI_BANNERS JSON string into a list."""
    raw = env_vars["WEBUI_BANNERS"]
    return json.loads(raw)


def test_banners_is_list(banners):
    """Req 1.10: WEBUI_BANNERS is a JSON array."""
    assert isinstance(banners, list)
    assert len(banners) >= 1


def test_banner_id(banners):
    """Req 1.10: Banner has the expected id."""
    assert banners[0]["id"] == "medical-disclaimer"


def test_banner_type(banners):
    """Req 6.3: Banner type is 'warning'."""
    assert banners[0]["type"] == "warning"


def test_banner_content(banners):
    """Req 6.1: Banner contains the medical disclaimer text."""
    content = banners[0]["content"]
    assert "Research Tool Only" in content
    assert "do not constitute medical advice" in content
    assert "healthcare professionals" in content


def test_banner_not_dismissible(banners):
    """Req 1.10, 6.1: Banner is non-dismissible."""
    assert banners[0]["dismissible"] is False


def test_banner_timestamp(banners):
    """Req 1.10: Banner has a timestamp field."""
    assert "timestamp" in banners[0]
    assert banners[0]["timestamp"] == 0


def test_banner_has_required_keys(banners):
    """Req 1.10: Banner contains all required BannerModel keys."""
    required_keys = {"id", "type", "content", "dismissible", "timestamp"}
    assert required_keys.issubset(set(banners[0].keys()))
