"""Unit tests for Workspace Model configuration.

Validates the workspace_model.json file against all Requirement 4 acceptance criteria (4.1–4.8).
"""

import json
import os

import pytest

# ---------------------------------------------------------------------------
# Fixture: load the workspace model JSON once
# ---------------------------------------------------------------------------

CONFIG_PATH = os.path.join(
    os.path.dirname(__file__), '..', 'config', 'workspace_model.json'
)


@pytest.fixture(scope="module")
def model():
    with open(CONFIG_PATH, 'r') as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Basic JSON validity
# ---------------------------------------------------------------------------

class TestWorkspaceModelJSONValidity:
    """The config file must be valid, parseable JSON."""

    def test_json_is_valid_and_parseable(self, model):
        assert isinstance(model, dict)


# ---------------------------------------------------------------------------
# Requirement 4.1 – Name and base model
# ---------------------------------------------------------------------------

class TestWorkspaceModelIdentity:
    """Validates: Requirement 4.1"""

    def test_id_is_rome_medical_assistant(self, model):
        assert model["id"] == "rome-medical-assistant"

    def test_name_is_rome_medical_assistant(self, model):
        assert model["name"] == "Rome Medical Assistant"

    def test_base_model_id_is_gpt_5_4(self, model):
        assert model["base_model_id"] == "gpt-5.4"


# ---------------------------------------------------------------------------
# Requirement 4.2 – Temperature and max tokens
# ---------------------------------------------------------------------------

class TestWorkspaceModelParams:
    """Validates: Requirement 4.2"""

    def test_temperature_is_0_2(self, model):
        assert model["params"]["temperature"] == 0.2

    def test_max_tokens_is_1024(self, model):
        assert model["params"]["max_tokens"] == 1024


# ---------------------------------------------------------------------------
# Requirement 4.5 / 4.6 – Capabilities
# ---------------------------------------------------------------------------

class TestWorkspaceModelCapabilities:
    """Validates: Requirements 4.5, 4.6"""

    def test_vision_is_false(self, model):
        assert model["meta"]["capabilities"]["vision"] is False

    def test_image_generation_is_false(self, model):
        assert model["meta"]["capabilities"]["image_generation"] is False

    def test_code_interpreter_is_false(self, model):
        assert model["meta"]["capabilities"]["code_interpreter"] is False

    def test_web_search_is_false(self, model):
        assert model["meta"]["capabilities"]["web_search"] is False

    def test_tool_use_is_true(self, model):
        assert model["meta"]["capabilities"]["tool_use"] is True


# ---------------------------------------------------------------------------
# Requirement 4.3 – Filter IDs
# ---------------------------------------------------------------------------

class TestWorkspaceModelFilterIds:
    """Validates: Requirement 4.3"""

    def test_filter_ids_contains_retrieval_filter(self, model):
        assert "zeroentropy-retrieval-filter" in model["meta"]["filterIds"]


# ---------------------------------------------------------------------------
# Requirement 4.4 – Tool IDs
# ---------------------------------------------------------------------------

class TestWorkspaceModelToolIds:
    """Validates: Requirement 4.4"""

    def test_tool_ids_contains_search_tool(self, model):
        assert "zeroentropy-search-tool" in model["meta"]["toolIds"]


# ---------------------------------------------------------------------------
# Requirement 4.7 – System prompt
# ---------------------------------------------------------------------------

class TestWorkspaceModelSystemPrompt:
    """Validates: Requirement 4.7"""

    def test_system_prompt_mentions_rome_v_medical_assistant(self, model):
        assert "Rome V Medical Assistant" in model["meta"]["system"]

    def test_system_prompt_mentions_dgbi(self, model):
        assert "DGBI" in model["meta"]["system"]

    def test_system_prompt_requires_citation(self, model):
        assert "cite the source" in model["meta"]["system"].lower() or \
               "cite" in model["meta"]["system"].lower()

    def test_system_prompt_declines_out_of_scope(self, model):
        assert "outside my area of expertise" in model["meta"]["system"].lower()


# ---------------------------------------------------------------------------
# Requirement 4.8 – Suggestion prompts
# ---------------------------------------------------------------------------

EXPECTED_TOPICS = {
    "IBS",
    "DGBI",
    "brain-gut",
    "questionnaire",
    "functional dyspepsia",
    "RFGES",
}


class TestWorkspaceModelSuggestionPrompts:
    """Validates: Requirement 4.8"""

    def test_suggestion_prompts_has_exactly_6_items(self, model):
        assert len(model["meta"]["suggestion_prompts"]) == 6

    def test_suggestion_prompts_cover_ibs(self, model):
        titles = [p["title"] for p in model["meta"]["suggestion_prompts"]]
        contents = [p["content"] for p in model["meta"]["suggestion_prompts"]]
        combined = " ".join(titles + contents)
        assert "IBS" in combined

    def test_suggestion_prompts_cover_dgbi_classification(self, model):
        titles = [p["title"] for p in model["meta"]["suggestion_prompts"]]
        contents = [p["content"] for p in model["meta"]["suggestion_prompts"]]
        combined = " ".join(titles + contents)
        assert "DGBI" in combined

    def test_suggestion_prompts_cover_brain_gut_axis(self, model):
        titles = [p["title"] for p in model["meta"]["suggestion_prompts"]]
        contents = [p["content"] for p in model["meta"]["suggestion_prompts"]]
        combined = " ".join(titles + contents).lower()
        assert "brain-gut" in combined or "brain gut" in combined

    def test_suggestion_prompts_cover_questionnaire_validation(self, model):
        titles = [p["title"] for p in model["meta"]["suggestion_prompts"]]
        contents = [p["content"] for p in model["meta"]["suggestion_prompts"]]
        combined = " ".join(titles + contents).lower()
        assert "questionnaire" in combined

    def test_suggestion_prompts_cover_functional_dyspepsia(self, model):
        titles = [p["title"] for p in model["meta"]["suggestion_prompts"]]
        contents = [p["content"] for p in model["meta"]["suggestion_prompts"]]
        combined = " ".join(titles + contents).lower()
        assert "functional dyspepsia" in combined

    def test_suggestion_prompts_cover_rfges_epidemiology(self, model):
        titles = [p["title"] for p in model["meta"]["suggestion_prompts"]]
        contents = [p["content"] for p in model["meta"]["suggestion_prompts"]]
        combined = " ".join(titles + contents)
        assert "RFGES" in combined or "Rome Foundation Global Epidemiology" in combined


# ---------------------------------------------------------------------------
# is_active flag
# ---------------------------------------------------------------------------

class TestWorkspaceModelActive:
    """The model must be active."""

    def test_is_active_is_true(self, model):
        assert model["is_active"] is True
