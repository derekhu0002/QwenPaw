import { useCallback, useEffect, useMemo, useState } from "react";
import { Button, Input, Modal, Select } from "@agentscope-ai/design";
import { Popconfirm, Space, Switch, Table, Tag } from "antd";
import type { ColumnsType } from "antd/es/table";
import { Plus } from "lucide-react";
import api from "../../../api";
import type {
  CredentialGovernancePolicy,
  CredentialGovernancePolicyPayload,
} from "../../../api/types";
import { PageHeader } from "../../../components/PageHeader";
import { useAppMessage } from "../../../hooks/useAppMessage";

function formatDate(ts: number): string {
  if (!ts) return "-";
  return new Date(ts * 1000).toLocaleString();
}

function parseStringArray(text: string, label: string): string[] {
  try {
    const value = JSON.parse(text);
    if (!Array.isArray(value)) {
      throw new Error(`${label} must be a JSON array`);
    }
    return value.map((item) => String(item)).filter(Boolean);
  } catch (error) {
    throw new Error(error instanceof Error ? error.message : `Invalid ${label}`);
  }
}

export default function CredentialPoliciesPage() {
  const { message } = useAppMessage();
  const [loading, setLoading] = useState(false);
  const [items, setItems] = useState<CredentialGovernancePolicy[]>([]);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<CredentialGovernancePolicy | null>(null);
  const [name, setName] = useState("");
  const [enabled, setEnabled] = useState(true);
  const [effect, setEffect] = useState<"permit" | "deny">("permit");
  const [agentId, setAgentId] = useState("");
  const [serviceId, setServiceId] = useState("");
  const [credentialId, setCredentialId] = useState("");
  const [allowedHostsJson, setAllowedHostsJson] = useState("[]");
  const [allowedMappedKeysJson, setAllowedMappedKeysJson] = useState("[]");
  const [cedarText, setCedarText] = useState("");

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.listCredentialGovernancePolicies();
      setItems(data);
    } catch (error) {
      message.error(error instanceof Error ? error.message : "Failed to load policies");
    } finally {
      setLoading(false);
    }
  }, [message]);

  useEffect(() => {
    void reload();
  }, [reload]);

  const resetModal = () => {
    setEditing(null);
    setName("");
    setEnabled(true);
    setEffect("permit");
    setAgentId("");
    setServiceId("");
    setCredentialId("");
    setAllowedHostsJson("[]");
    setAllowedMappedKeysJson("[]");
    setCedarText("");
  };

  const openCreate = () => {
    resetModal();
    setOpen(true);
  };

  const openEdit = (item: CredentialGovernancePolicy) => {
    setEditing(item);
    setName(item.name);
    setEnabled(item.enabled);
    setEffect(item.effect);
    setAgentId(item.agent_id || "");
    setServiceId(item.service_id || "");
    setCredentialId(item.credential_id || "");
    setAllowedHostsJson(JSON.stringify(item.allowed_hosts || [], null, 2));
    setAllowedMappedKeysJson(
      JSON.stringify(item.allowed_mapped_keys || [], null, 2),
    );
    setCedarText(item.cedar_text || "");
    setOpen(true);
  };

  const submit = async () => {
    let allowedHosts: string[];
    let allowedMappedKeys: string[];
    try {
      allowedHosts = parseStringArray(allowedHostsJson, "Allowed hosts");
      allowedMappedKeys = parseStringArray(
        allowedMappedKeysJson,
        "Allowed mapped keys",
      );
    } catch (error) {
      message.error(error instanceof Error ? error.message : "Invalid policy");
      return;
    }

    const payload: CredentialGovernancePolicyPayload = {
      name,
      enabled,
      effect,
      agent_id: agentId,
      service_id: serviceId,
      credential_id: credentialId,
      allowed_hosts: allowedHosts,
      allowed_mapped_keys: allowedMappedKeys,
      cedar_text: cedarText,
    };

    try {
      if (editing) {
        await api.updateCredentialGovernancePolicy(editing.id, payload);
      } else {
        await api.createCredentialGovernancePolicy(payload);
      }
      setOpen(false);
      resetModal();
      await reload();
      message.success("Policy saved");
    } catch (error) {
      message.error(error instanceof Error ? error.message : "Save failed");
    }
  };

  const toggleEnabled = async (item: CredentialGovernancePolicy, value: boolean) => {
    try {
      await api.updateCredentialGovernancePolicy(item.id, { enabled: value });
      await reload();
    } catch (error) {
      message.error(error instanceof Error ? error.message : "Update failed");
    }
  };

  const remove = async (item: CredentialGovernancePolicy) => {
    try {
      await api.deleteCredentialGovernancePolicy(item.id);
      await reload();
      message.success("Policy deleted");
    } catch (error) {
      message.error(error instanceof Error ? error.message : "Delete failed");
    }
  };

  const columns: ColumnsType<CredentialGovernancePolicy> = useMemo(
    () => [
      { title: "Name", dataIndex: "name" },
      {
        title: "Enabled",
        dataIndex: "enabled",
        render: (value: boolean, item) => (
          <Switch checked={value} onChange={(next) => void toggleEnabled(item, next)} />
        ),
      },
      {
        title: "Effect",
        dataIndex: "effect",
        render: (value: string) => (
          <Tag color={value === "permit" ? "green" : "red"}>{value}</Tag>
        ),
      },
      { title: "Agent", dataIndex: "agent_id", render: (value?: string) => value || "*" },
      {
        title: "Service",
        dataIndex: "service_id",
        render: (value?: string) => value || "*",
      },
      {
        title: "Credential",
        dataIndex: "credential_id",
        render: (value?: string) => value || "*",
      },
      {
        title: "Allowed Hosts",
        dataIndex: "allowed_hosts",
        render: (value: string[]) => (value || []).join(", ") || "*",
      },
      {
        title: "Allowed Keys",
        dataIndex: "allowed_mapped_keys",
        render: (value: string[]) => (value || []).join(", ") || "*",
      },
      { title: "Updated", dataIndex: "updated_at", render: formatDate },
      {
        title: "Actions",
        render: (_, item) => (
          <Space>
            <Button size="small" onClick={() => openEdit(item)}>
              Edit
            </Button>
            <Popconfirm title="Delete this policy?" onConfirm={() => void remove(item)}>
              <Button size="small" danger>
                Delete
              </Button>
            </Popconfirm>
          </Space>
        ),
      },
    ],
    [],
  );

  return (
    <div>
      <PageHeader
        items={[{ title: "Settings" }, { title: "Credential Policies" }]}
        extra={
          <Space>
            <Button onClick={() => void reload()}>Refresh</Button>
            <Button type="primary" icon={<Plus size={14} />} onClick={openCreate}>
              Create Policy
            </Button>
          </Space>
        }
      />

      <div style={{ marginBottom: 12 }}>
        <Tag color="blue">Local policy engine</Tag>
        <Tag>Cedar text is stored for future sidecar integration</Tag>
      </div>

      <Table
        rowKey="id"
        columns={columns}
        dataSource={items}
        loading={loading}
        pagination={{ pageSize: 10 }}
      />

      <Modal
        title={editing ? "Edit Credential Policy" : "Create Credential Policy"}
        open={open}
        onCancel={() => {
          setOpen(false);
          resetModal();
        }}
        onOk={() => void submit()}
        width={760}
      >
        <Space direction="vertical" style={{ width: "100%" }}>
          <Input placeholder="Name" value={name} onChange={(e) => setName(e.target.value)} />
          <Space>
            <Switch checked={enabled} onChange={setEnabled} />
            <span>Enabled</span>
          </Space>
          <Select
            value={effect}
            options={[
              { label: "Permit", value: "permit" },
              { label: "Deny", value: "deny" },
            ]}
            onChange={(value) => setEffect(value as "permit" | "deny")}
          />
          <Input
            placeholder="Agent ID, empty means any"
            value={agentId}
            onChange={(e) => setAgentId(e.target.value)}
          />
          <Input
            placeholder="Service ID, e.g. mcp:github, empty means any"
            value={serviceId}
            onChange={(e) => setServiceId(e.target.value)}
          />
          <Input
            placeholder="Credential ID, empty means any"
            value={credentialId}
            onChange={(e) => setCredentialId(e.target.value)}
          />
          <Input.TextArea
            rows={3}
            value={allowedHostsJson}
            placeholder={'Allowed hosts JSON, empty array means any: ["api.github.com"]'}
            onChange={(e) => setAllowedHostsJson(e.target.value)}
          />
          <Input.TextArea
            rows={3}
            value={allowedMappedKeysJson}
            placeholder={'Allowed mapped keys JSON, empty array means all: ["header.Authorization"]'}
            onChange={(e) => setAllowedMappedKeysJson(e.target.value)}
          />
          <Input.TextArea
            rows={6}
            value={cedarText}
            placeholder="Optional Cedar policy text for future sidecar integration"
            onChange={(e) => setCedarText(e.target.value)}
          />
        </Space>
      </Modal>
    </div>
  );
}
