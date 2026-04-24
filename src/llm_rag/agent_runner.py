"""AgentDefinition and run_agent() — shared subagent runner.

This module provides a lightweight runner for Claude-backed agents that:

1. Loads a system prompt from ``agents/prompts/<name>.md``.
2. Wires up MCP servers (if any) using their ``MCPServerConfig.command`` via the
   claude-code-sdk ``ClaudeCodeOptions.mcp_servers`` dict.
3. Streams the claude-code-sdk ``query()`` response and concatenates all
   ``TextBlock`` content from ``AssistantMessage`` objects into a final string.

The claude-code-sdk ``query()`` function spawns a ``claude`` CLI subprocess under
the hood, so no long-lived connection management is needed here — ``MCPPool`` is
consulted only for its stored ``configs`` (to get the MCP server command), not for
its live ``ClientSession`` objects.

Usage::

    defn = AgentDefinition(
        name="extraction",
        model=settings.model_bulk_extraction,
        mcp_servers=["corpus-io"],
    )
    async with MCPPool() as pool:
        result = await run_agent(defn, "Extract entities from ...", settings, pool)
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from llm_rag.config import Settings
from llm_rag.mcp.pool import MCPPool

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Typed exceptions for contract violations
# ---------------------------------------------------------------------------


class ToolResultContractError(Exception):
    """Raised when a tool call returns data that violates the expected schema.

    Attributes
    ----------
    tool_name:
        The MCP tool whose result failed validation.
    expected_schema:
        Name of the Pydantic model that the result should conform to.
    details:
        Human-readable description of what went wrong.
    raw_result:
        The raw result data that failed validation (may be truncated).
    """

    def __init__(
        self,
        tool_name: str,
        expected_schema: str,
        details: str,
        raw_result: Any = None,
    ) -> None:
        self.tool_name = tool_name
        self.expected_schema = expected_schema
        self.details = details
        self.raw_result = raw_result
        super().__init__(
            f"Tool {tool_name!r} result violates {expected_schema} contract: {details}"
        )


def validate_tool_result(
    tool_name: str,
    result: Any,
    schema: type[BaseModel],
) -> BaseModel:
    """Validate a tool call result against a Pydantic model.

    Parameters
    ----------
    tool_name:
        Logical name of the tool (for error messages).
    result:
        The raw result — either a dict, a JSON string, or a list of dicts.
    schema:
        The Pydantic model class to validate against.

    Returns
    -------
    BaseModel
        The validated Pydantic model instance.

    Raises
    ------
    ToolResultContractError
        If the result cannot be parsed or does not conform to the schema.
    """
    data: Any = result

    # If result is a string, attempt JSON parse
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except json.JSONDecodeError as exc:
            raise ToolResultContractError(
                tool_name=tool_name,
                expected_schema=schema.__name__,
                details=f"Result is not valid JSON: {exc}",
                raw_result=result[:500] if isinstance(result, str) else result,
            ) from exc

    if not isinstance(data, dict):
        raise ToolResultContractError(
            tool_name=tool_name,
            expected_schema=schema.__name__,
            details=f"Expected dict, got {type(data).__name__}",
            raw_result=data,
        )

    try:
        return schema.model_validate(data)
    except ValidationError as exc:
        raise ToolResultContractError(
            tool_name=tool_name,
            expected_schema=schema.__name__,
            details=str(exc),
            raw_result=data,
        ) from exc


def validate_tool_result_list(
    tool_name: str,
    result: Any,
    schema: type[BaseModel],
) -> list[BaseModel]:
    """Validate a tool call result that should be a list of schema-conforming items.

    Parameters
    ----------
    tool_name:
        Logical name of the tool (for error messages).
    result:
        The raw result — either a list of dicts or a JSON string encoding one.
    schema:
        The Pydantic model class each item should validate against.

    Returns
    -------
    list[BaseModel]
        List of validated Pydantic model instances.

    Raises
    ------
    ToolResultContractError
        If the result is not a list or any item fails validation.
    """
    data: Any = result

    if isinstance(data, str):
        try:
            data = json.loads(data)
        except json.JSONDecodeError as exc:
            raise ToolResultContractError(
                tool_name=tool_name,
                expected_schema=f"list[{schema.__name__}]",
                details=f"Result is not valid JSON: {exc}",
                raw_result=result[:500] if isinstance(result, str) else result,
            ) from exc

    if not isinstance(data, list):
        raise ToolResultContractError(
            tool_name=tool_name,
            expected_schema=f"list[{schema.__name__}]",
            details=f"Expected list, got {type(data).__name__}",
            raw_result=data,
        )

    validated: list[BaseModel] = []
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            raise ToolResultContractError(
                tool_name=tool_name,
                expected_schema=f"list[{schema.__name__}]",
                details=f"Item {i} is {type(item).__name__}, expected dict",
                raw_result=item,
            )
        try:
            validated.append(schema.model_validate(item))
        except ValidationError as exc:
            raise ToolResultContractError(
                tool_name=tool_name,
                expected_schema=f"list[{schema.__name__}]",
                details=f"Item {i} validation failed: {exc}",
                raw_result=item,
            ) from exc

    return validated


# ---------------------------------------------------------------------------
# AgentDefinition
# ---------------------------------------------------------------------------


@dataclass
class AgentDefinition:
    """Declarative description of a Claude-backed agent.

    Parameters
    ----------
    name:
        Logical agent name, used to locate the system prompt at
        ``agents/prompts/<name>.md``.
    model:
        Claude model identifier, e.g. ``"claude-haiku-4-5-20251001"``.
    mcp_servers:
        Ordered list of MCP server logical names to wire up.  Each name must
        correspond to an ``MCPServerConfig.name`` entry in the ``MCPPool``
        that is passed to :func:`run_agent`.
    max_tokens:
        Maximum tokens Claude may generate in a single turn.
    """

    name: str
    model: str
    mcp_servers: list[str] = field(default_factory=list)
    max_tokens: int = 8192

    def prompt_path(self, settings: Settings) -> Path:
        """Return the absolute path to this agent's system-prompt file.

        Parameters
        ----------
        settings:
            Settings instance used to resolve ``agents_dir``.

        Returns
        -------
        Path
            ``<agents_dir>/prompts/<name>.md``
        """
        return settings.agents_dir / "prompts" / f"{self.name}.md"


# ---------------------------------------------------------------------------
# run_agent()
# ---------------------------------------------------------------------------


async def run_agent(
    definition: AgentDefinition,
    user_message: str,
    settings: Settings,
    mcp_pool: MCPPool,
) -> str:
    """Run a Claude agent and return its final text response.

    Uses the claude-code-sdk ``query()`` function to submit a one-shot prompt
    with the agent's system prompt and any configured MCP servers.

    Parameters
    ----------
    definition:
        :class:`AgentDefinition` that declares the agent's name, model, and
        MCP server requirements.
    user_message:
        The user-turn message to send to Claude.
    settings:
        Application settings (used to locate the prompt file).
    mcp_pool:
        An active :class:`~llm_rag.mcp.pool.MCPPool`.  Its ``configs`` are
        inspected to retrieve the MCP server command for each name listed in
        ``definition.mcp_servers``.

    Returns
    -------
    str
        The concatenated text from all ``AssistantMessage`` / ``TextBlock``
        objects emitted by Claude.  Returns an empty string if Claude produces
        no text output.

    Raises
    ------
    FileNotFoundError
        If the system prompt file does not exist at the expected path.
    KeyError
        If a requested MCP server name is not registered in the pool's configs.
    """
    # Lazy import to avoid module-level failures when the SDK is unavailable.
    from claude_code_sdk import query
    from claude_code_sdk.types import (
        AssistantMessage,
        ClaudeCodeOptions,
        McpHttpServerConfig,
        McpSdkServerConfig,
        McpSSEServerConfig,
        McpStdioServerConfig,
        TextBlock,
    )

    # ------------------------------------------------------------------
    # 1. Load system prompt
    # ------------------------------------------------------------------
    prompt_file = definition.prompt_path(settings)
    if not prompt_file.exists():
        raise FileNotFoundError(
            f"Agent system-prompt not found: {prompt_file}"
        )
    system_prompt = prompt_file.read_text(encoding="utf-8")

    # ------------------------------------------------------------------
    # 2. Build MCP server config dict for ClaudeCodeOptions
    # ------------------------------------------------------------------
    # Index the pool's configs by name for O(1) lookup.
    config_by_name = {cfg.name: cfg for cfg in mcp_pool.configs}

    mcp_servers_cfg: dict[
        str,
        McpStdioServerConfig | McpSSEServerConfig | McpHttpServerConfig | McpSdkServerConfig,
    ] = {}
    for server_name in definition.mcp_servers:
        if server_name not in config_by_name:
            raise KeyError(
                f"MCP server {server_name!r} is not registered in the pool.  "
                f"Known servers: {list(config_by_name)}"
            )
        cfg = config_by_name[server_name]
        command, *args = cfg.command
        mcp_server_cfg = McpStdioServerConfig(
            command=command,
            args=args,
            type="stdio",
        )
        if cfg.env:
            mcp_server_cfg["env"] = cfg.env
        mcp_servers_cfg[server_name] = mcp_server_cfg

    # ------------------------------------------------------------------
    # 3. Build ClaudeCodeOptions
    # ------------------------------------------------------------------
    options = ClaudeCodeOptions(
        system_prompt=system_prompt,
        model=definition.model,
        mcp_servers=mcp_servers_cfg,
        max_turns=1,
        permission_mode="bypassPermissions",
    )

    # ------------------------------------------------------------------
    # 4. Stream response and collect text
    # ------------------------------------------------------------------
    text_parts: list[str] = []

    async for message in query(prompt=user_message, options=options):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    text_parts.append(block.text)

    result = "".join(text_parts)
    logger.debug(
        "run_agent(%r) → %d chars", definition.name, len(result)
    )
    return result
