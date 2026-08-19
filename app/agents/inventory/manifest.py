from app.knowledge.policy import AgentKnowledgePolicy


AGENT_ID = "inventory-agent"
KNOWLEDGE_POLICY = AgentKnowledgePolicy(
    private_domain="inventory",
    allowed_domains=frozenset({"inventory", "shared"}),
)
