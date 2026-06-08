import { useCallback, useEffect, useMemo, useState } from "react";
import { Button, Input, Modal, Select } from "@agentscope-ai/design";
import { Popconfirm, Space, Table, Tag } from "antd";
import type { ColumnsType } from "antd/es/table";
import { Plus } from "lucide-react";
import api, { agentsApi } from "../../../api";
import type {
  AgentSummary,
  CredentialCreateRequest,
  CredentialItem,
  CredentialScope,
  CredentialType,
} from "../../../api/types";
import { useAppMessage } from "../../../hooks/useAppMessage";
import { PageHeader } from "../../../components/PageHeader";
import { useAgentStore } from "../../../stores/agentStore";

const TYPE_OPTIONS: Array<{ label: string; value: CredentialType }> = [
  { label: "AK/SK", value: "aksk" },
  { label: "Token", value: "token" },
  { label: "API Key", value: "api_key" },
  { label: "Cookie", value: "cookie" },
  { label: "Custom KV", value: "custom_kv" },
];

function formatDate(ts: number): string {
  if (!ts) return "-";
  return new Date(ts * 1000).toLocaleString();
}

export default function CredentialsPage() {
  const { message } = useAppMessage();
  const { selectedAgent } = useAgentStore();
  const [loading, setLoading] = useState(false);
  const [items, setItems] = useState<CredentialItem[]>([]);
  const [agents, setAgents] = useState<AgentSummary[]>([]);
  const [scope, setScope] = useState<CredentialScope>("visible");
  const [agentId, setAgentId] = useState(selectedAgent || "");

  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<CredentialItem | null>(null);
  const [viewing, setViewing] = useState<CredentialItem | null>(null);
  const [viewOpen, setViewOpen] = useState(false);
  const [viewJsonData, setViewJsonData] = useState("{}");
  const [name, setName] = useState("");
  const [type, setType] = useState<CredentialType>("custom_kv");
  const [entryScope, setEntryScope] = useState<"agent" | "global">("agent");
  const [description, setDescription] = useState("");
  const [jsonData, setJsonData] = useState('{\n  "api_key": ""\n}');
  const resolvedAgentId = agentId.trim();

  useEffect(() => {
    if (!agentId && selectedAgent) {
      setAgentId(selectedAgent);
    }
  }, [agentId, selectedAgent]);

  useEffect(() => {
    const loadAgents = async () => {
      try {
        const listResp = await agentsApi.listAgents();
        setAgents(listResp.agents || []);
      } catch {
        setAgents([]);
      }
    };
    void loadAgents();
  }, []);

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      if (scope === "global") {
        const data = await api.listCredentials("global");
        setItems(data);
        return;
      }
      if (!resolvedAgentId) {
        const [globalItems, listResp] = await Promise.all([
          api.listCredentials("global"),
          agentsApi.listAgents(),
        ]);
        const agentItemsNested = await Promise.all(
          (listResp.agents || []).map(async (agent: { id: string }) => {
            try {
              return await api.listCredentials("agent", agent.id);
            } catch {
              return [] as CredentialItem[];
            }
          }),
        );
        const merged = [...globalItems, ...agentItemsNested.flat()];
        const deduped = Array.from(
          new Map(
            merged.map((item) => [
              `${item.scope}:${item.agent_id || ""}:${item.id}`,
              item,
            ]),
          ).values(),
        );
        setItems(deduped);
        message.warning("未选择 Agent ID，已展示全部可见凭据");
        return;
      }
      const data = await api.listCredentials("visible", resolvedAgentId);
      setItems(data);
    } catch (error) {
      message.error(error instanceof Error ? error.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  }, [message, resolvedAgentId, scope]);

  useEffect(() => {
    void reload();
  }, [reload]);

  const resetModal = useCallback(() => {
    setEditing(null);
    setName("");
    setType("custom_kv");
    setEntryScope("agent");
    setDescription("");
    setJsonData('{\n  "api_key": ""\n}');
  }, []);

  const openCreate = () => {
    if (scope !== "global" && !resolvedAgentId) {
      message.warning("请先选择 Agent ID");
      return;
    }
    resetModal();
    setEntryScope(scope === "global" ? "global" : "agent");
    setOpen(true);
  };

  const loadCredentialDetail = useCallback(
    async (item: CredentialItem) => {
      let detailScope: CredentialScope = "global";
      let detailAgentId: string | undefined;
      if (scope === "global") {
        detailScope = "global";
      } else if (resolvedAgentId) {
        detailScope = "visible";
        detailAgentId = resolvedAgentId;
      } else {
        detailScope = item.scope === "global" ? "global" : "agent";
        detailAgentId = item.scope === "agent" ? item.agent_id || undefined : undefined;
      }
      return api.getCredential(item.id, detailScope, detailAgentId);
    },
    [resolvedAgentId, scope],
  );

  const openEdit = async (item: CredentialItem) => {
    try {
      const detail = await loadCredentialDetail(item);
      setEditing(detail);
      setName(detail.name);
      setType(detail.type);
      setEntryScope(detail.scope);
      setDescription(detail.description);
      setJsonData(JSON.stringify(detail.data, null, 2));
      setOpen(true);
    } catch (error) {
      message.error(error instanceof Error ? error.message : "Failed to load credential detail");
    }
  };

  const openView = async (item: CredentialItem) => {
    try {
      const detail = await loadCredentialDetail(item);
      setViewing(detail);
      setViewJsonData(JSON.stringify(detail.data, null, 2));
      setViewOpen(true);
    } catch (error) {
      message.error(error instanceof Error ? error.message : "Failed to load credential detail");
    }
  };

  const submit = async () => {
    let parsed: Record<string, string>;
    try {
      const value = JSON.parse(jsonData);
      if (!value || typeof value !== "object" || Array.isArray(value)) {
        message.error("Data must be a JSON object");
        return;
      }
      parsed = Object.entries(value).reduce<Record<string, string>>(
        (acc, [k, v]) => {
          acc[k] = String(v ?? "");
          return acc;
        },
        {},
      );
    } catch {
      message.error("Invalid JSON data");
      return;
    }

    try {
      if (!editing && entryScope === "agent" && !resolvedAgentId) {
        message.error("Agent 级凭据必须选择 Agent ID");
        return;
      }
      if (editing) {
        await api.updateCredential(
          editing.id,
          { name, type, description, data: parsed },
          editing.scope,
          editing.scope === "agent"
            ? editing.agent_id || resolvedAgentId || undefined
            : undefined,
        );
      } else {
        const payload: CredentialCreateRequest = {
          name,
          type,
          scope: entryScope,
          agent_id: entryScope === "agent" ? resolvedAgentId || undefined : undefined,
          description,
          data: parsed,
        };
        await api.createCredential(payload);
      }
      setOpen(false);
      resetModal();
      await reload();
      message.success("Saved");
    } catch (error) {
      message.error(error instanceof Error ? error.message : "Save failed");
    }
  };

  const remove = async (item: CredentialItem) => {
    try {
      await api.deleteCredential(
        item.id,
        item.scope,
        item.scope === "agent" ? item.agent_id || resolvedAgentId || undefined : undefined,
      );
      await reload();
      message.success("Deleted");
    } catch (error) {
      message.error(error instanceof Error ? error.message : "Delete failed");
    }
  };

  const columns: ColumnsType<CredentialItem> = useMemo(
    () => [
      { title: "Name", dataIndex: "name", key: "name" },
      {
        title: "Type",
        dataIndex: "type",
        key: "type",
        render: (value: CredentialType) => <Tag>{value}</Tag>,
      },
      {
        title: "Agent ID",
        dataIndex: "agent_id",
        key: "agent_id",
        render: (value?: string) => value || "-",
      },
      {
        title: "Scope",
        dataIndex: "scope",
        key: "scope",
        render: (value: string) => (
          <Tag color={value === "agent" ? "green" : "geekblue"}>{value}</Tag>
        ),
      },
      { title: "Updated", dataIndex: "updated_at", render: formatDate },
      {
        title: "Actions",
        key: "actions",
        render: (_, item) => (
          <Space>
            <Button size="small" onClick={() => void openView(item)}>
              View
            </Button>
            <Button size="small" onClick={() => void openEdit(item)}>
              Edit
            </Button>
            <Popconfirm
              title="Delete this credential?"
              onConfirm={() => void remove(item)}
            >
              <Button size="small" danger>
                Delete
              </Button>
            </Popconfirm>
          </Space>
        ),
      },
    ],
    [openEdit, openView],
  );

  const agentOptions = useMemo(() => {
    const base = agents.map((agent) => ({
      label: `${agent.name || agent.id} (${agent.id})`,
      value: agent.id,
    }));
    if (resolvedAgentId && !base.some((agent) => agent.value === resolvedAgentId)) {
      return [
        ...base,
        { label: `${resolvedAgentId} (manual)`, value: resolvedAgentId },
      ];
    }
    return base;
  }, [agents, resolvedAgentId]);

  return (
    <div>
      <PageHeader
        items={[{ title: "Settings" }, { title: "Credentials" }]}
        extra={
          <Space>
            <Select
              value={scope}
              style={{ width: 160 }}
              options={[
                { label: "Agent Visible", value: "visible" },
                { label: "Global", value: "global" },
              ]}
              onChange={(value) => setScope(value as CredentialScope)}
            />
            <Select
              value={agentId || undefined}
              style={{ width: 320 }}
              placeholder="选择或搜索 Agent ID"
              showSearch
              options={agentOptions}
              disabled={scope === "global"}
              filterOption={(input, option) =>
                String(option?.label ?? "")
                  .toLowerCase()
                  .includes(input.toLowerCase())
              }
              onChange={(value) => setAgentId((value as string) || "")}
            />
            <Button onClick={() => void reload()}>Refresh</Button>
            <Button type="primary" icon={<Plus size={14} />} onClick={openCreate}>
              Create
            </Button>
          </Space>
        }
      />

      <div style={{ marginBottom: 12 }}>
        <Tag color={resolvedAgentId ? "green" : "default"}>
          {scope === "global"
            ? "Current Scope: Global"
            : resolvedAgentId
              ? `Current Agent: ${resolvedAgentId}`
              : "Current Agent: not selected"}
        </Tag>
      </div>

      <Table
        rowKey="id"
        columns={columns}
        dataSource={items}
        loading={loading}
        pagination={{ pageSize: 10 }}
      />

      <Modal
        title={editing ? "Edit Credential" : "Create Credential"}
        open={open}
        onCancel={() => {
          setOpen(false);
          resetModal();
        }}
        onOk={() => void submit()}
      >
        <Space direction="vertical" style={{ width: "100%" }}>
          <Input
            placeholder="Name"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
          <Select
            value={type}
            options={TYPE_OPTIONS}
            onChange={(value) => setType(value as CredentialType)}
          />
          {!editing && (
            <Select
              value={entryScope}
              options={[
                { label: "Agent", value: "agent" },
                { label: "Global", value: "global" },
              ]}
              onChange={(value) => setEntryScope(value as "agent" | "global")}
            />
          )}
          {!editing && entryScope === "agent" && (
            <Input value={resolvedAgentId} readOnly placeholder="Agent ID" />
          )}
          {editing && editing.scope === "agent" && (
            <Input value={editing.agent_id || "-"} readOnly placeholder="Agent ID" />
          )}
          <Input
            placeholder="Description"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
          <Input.TextArea
            rows={8}
            value={jsonData}
            onChange={(e) => setJsonData(e.target.value)}
          />
        </Space>
      </Modal>

      <Modal
        title={viewing ? `Credential Data: ${viewing.name}` : "Credential Data"}
        open={viewOpen}
        onCancel={() => {
          setViewOpen(false);
          setViewing(null);
          setViewJsonData("{}");
        }}
        footer={null}
      >
        <Space direction="vertical" style={{ width: "100%" }}>
          {viewing && (
            <Tag color={viewing.scope === "global" ? "geekblue" : "green"}>
              {viewing.scope === "global"
                ? "Global Credential"
                : `Agent Credential (${viewing.agent_id || "-"})`}
            </Tag>
          )}
          <Input.TextArea rows={12} value={viewJsonData} readOnly />
        </Space>
      </Modal>
    </div>
  );
}

