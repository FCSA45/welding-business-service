from app.knowledge.policy import AgentKnowledgePolicy


AGENT_ID = "workshop-agent"
KNOWLEDGE_POLICY = AgentKnowledgePolicy(
    private_domain="workshop",
    allowed_domains=frozenset({"workshop", "shared"}),
)
