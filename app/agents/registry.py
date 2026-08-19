from app.agents.inventory.manifest import (
    AGENT_ID as INVENTORY_AGENT_ID,
    KNOWLEDGE_POLICY as INVENTORY_KNOWLEDGE_POLICY,
)
from app.agents.workshop.manifest import (
    AGENT_ID as WORKSHOP_AGENT_ID,
    KNOWLEDGE_POLICY as WORKSHOP_KNOWLEDGE_POLICY,
)
from app.agents.painting.manifest import (
    AGENT_ID as PAINTING_AGENT_ID,
    KNOWLEDGE_POLICY as PAINTING_KNOWLEDGE_POLICY,
)


AGENT_KNOWLEDGE_POLICIES = {
    WORKSHOP_AGENT_ID: WORKSHOP_KNOWLEDGE_POLICY,
    PAINTING_AGENT_ID: PAINTING_KNOWLEDGE_POLICY,
    INVENTORY_AGENT_ID: INVENTORY_KNOWLEDGE_POLICY,
}

# Canonical metadata used to bootstrap a fresh development database.  Keeping
# this next to the manifests prevents startup scripts from inventing a second
# set of agent identifiers.
BUILTIN_AGENTS = (
    {
        "id": WORKSHOP_AGENT_ID,
        "name": "车间智能体",
        "group_name": "生产中心",
        "description": "查询车间订单、工序和报工数据，并生成部门日报。",
        "system_prompt": "你是车间生产运营智能体。用户问候或询问功能时，直接说明可查询订单日报、报工日报、订单详情、报工明细和业务知识，不调用业务数据工具。执行业务查询时必须先确认日期、订单号或人员等必要参数；所有数字、状态、日期和结论只能来自本轮授权工具结果，工具无数据、报错或缺字段时必须如实说明，不得编造、估算、反推或用历史记忆补全。查询订单工序详情时，必须将工具返回的订单号编码和产品名称分两行显示，不能只显示订单号或把两者合并。只服务已通过企业微信身份和部门权限校验的内部员工。",
        "status": "active",
        "enabled": True,
    },
    {
        "id": INVENTORY_AGENT_ID,
        "name": "库存智能体",
        "group_name": "供应链",
        "description": "库存数据查询与分析。",
        "system_prompt": "你是库存智能体。必须以授权数据源的真实数据为准。",
        "status": "planned",
        "enabled": False,
    },
    {
        "id": PAINTING_AGENT_ID,
        "name": "油漆部智能体",
        "group_name": "生产中心",
        "description": "查询油漆部订单、工序、报工与部门日常生产信息。",
        "system_prompt": "你是油漆部生产运营智能体。用户问候或询问功能时，直接说明可查询订单日报、报工日报、订单详情、报工明细和业务知识，不调用业务数据工具。只能依据已授权的油漆部业务数据、油漆部知识库和共享制度资料回答；数据不足、工具报错或缺字段时必须如实说明，不得编造、估算、反推或用历史记忆补全订单、产量、进度或异常原因。查询订单工序详情时，必须将工具返回的订单号编码和产品名称分两行显示，不能只显示订单号或把两者合并。只服务已通过企业微信身份和部门权限校验的内部员工。",
        "status": "active",
        "enabled": True,
    },
)
