const assert = require('assert');
const fs = require('fs');
const path = require('path');

const repoRoot = path.resolve(__dirname, '..', '..');

const explicitSecurityEventTestcases = [
    {
        testcaseName: 'sec-event-ingestion-v1-accept-legal-event',
        entryPath: 'tests/integration/security/test_security_event_ingestion.py::test_accepts_legal_event_after_persistence',
        marker: 'def test_accepts_legal_event_after_persistence',
        category: 'Security_Event_Acceptance_Gap',
    },
    {
        testcaseName: 'sec-event-ingestion-v1-reject-invalid-config-boundary',
        entryPath: 'tests/integration/security/test_security_event_ingestion.py::test_rejects_invalid_event_config_boundary',
        marker: 'def test_rejects_invalid_event_config_boundary',
        category: 'Security_Event_Rejection_Gap',
    },
    {
        testcaseName: 'sec-event-ingestion-v1-preserve-undefined-payload-fields',
        entryPath: 'tests/integration/security/test_security_event_ingestion.py::test_preserves_undefined_payload_fields_in_detail_only',
        marker: 'def test_preserves_undefined_payload_fields_in_detail_only',
        category: 'Security_Event_Undefined_Field_Gap',
    },
    {
        testcaseName: 'sec-event-ingestion-v1-enforce-idempotency',
        entryPath: 'tests/integration/security/test_security_event_ingestion.py::test_enforces_source_event_id_idempotency',
        marker: 'def test_enforces_source_event_id_idempotency',
        category: 'Security_Event_Idempotency_Gap',
    },
    {
        testcaseName: 'sec-event-ingestion-v1-render-web-list-and-detail',
        entryPath: 'tests/e2e/security_center/test_security_event_inbox.py::test_web_lists_filters_and_opens_event_detail',
        marker: 'def test_web_lists_filters_and_opens_event_detail',
        category: 'Security_Event_Inbox_Web_Gap',
    },
    {
        testcaseName: 'sec-event-ingestion-v1-bound-failure-records',
        entryPath: 'tests/integration/security/test_security_event_ingestion.py::test_records_failed_receptions_without_business_event_pollution',
        marker: 'def test_records_failed_receptions_without_business_event_pollution',
        category: 'Security_Event_Failure_Record_Gap',
    },
];

function readText(relativePath) {
    return fs.readFileSync(path.join(repoRoot, ...relativePath.split('/')), 'utf8');
}

function readJson(relativePath) {
    return JSON.parse(readText(relativePath));
}

const graph = readJson('design/KG/SystemArchitecture.json');
const handoff = readJson('design/KG/ImplementationToCodingHandoff.json');
const integrationTestBody = readText('tests/integration/security/test_security_event_ingestion.py');
const webTestBody = readText('tests/e2e/security_center/test_security_event_inbox.py');
const harnessBody = readText('tests/integration/security/security_event_harness.py');
const rootContract = readText('OVERALL_ARCHITECTURE.md');
const deployApiContract = readText('deploy/api/ARCHITECTURE.md');
const deployWebContract = readText('deploy/web/ARCHITECTURE.md');
const testsContract = readText('tests/ARCHITECTURE.md');
const integrationContract = readText('tests/integration/security/ARCHITECTURE.md');
const e2eContract = readText('tests/e2e/security_center/ARCHITECTURE.md');
const eventConfig = readJson('deploy/config/security-event-contracts.v1.json');

for (const explicitTestcase of explicitSecurityEventTestcases) {
    const graphTestcase = (graph.elements || [])
        .flatMap(element => element.testcases || [])
        .find(testcase => testcase.name === explicitTestcase.testcaseName);

    assert.ok(graphTestcase, `SystemArchitecture.json must include ${explicitTestcase.testcaseName}.`);
    assert.strictEqual(
        graphTestcase.acceptanceCriteria,
        explicitTestcase.entryPath,
        `${explicitTestcase.testcaseName} must stay mounted to the frozen explicit entrypoint.`,
    );

    const handoffEntrypoint = (handoff.explicitEntrypoints || []).find(
        entry => entry.testcaseName === explicitTestcase.testcaseName,
    );
    assert.ok(handoffEntrypoint, `Implementation handoff must include ${explicitTestcase.testcaseName}.`);
    assert.strictEqual(handoffEntrypoint.entryPath, explicitTestcase.entryPath);
    assert.strictEqual(
        handoffEntrypoint.initialExecutionStatus,
        'failed',
        `${explicitTestcase.testcaseName} must remain an expected failing Coding/Repair input until implemented.`,
    );

    const body = explicitTestcase.entryPath.startsWith('tests/e2e/')
        ? webTestBody
        : integrationTestBody;
    assert.ok(body.includes(explicitTestcase.marker), `Missing test marker ${explicitTestcase.marker}.`);
    assert.ok(body.includes('# // GIVEN'), `${explicitTestcase.testcaseName} must keep GIVEN marker.`);
    assert.ok(body.includes('# // WHEN'), `${explicitTestcase.testcaseName} must keep WHEN marker.`);
    assert.ok(body.includes('# // THEN'), `${explicitTestcase.testcaseName} must keep THEN marker.`);
    assert.ok(harnessBody.includes(explicitTestcase.category), `Harness must expose ${explicitTestcase.category}.`);
}

for (const marker of [
    '/security-center/v1/events',
    '/security-center/v1/operator/events',
    '/security-center/v1/operator/event-reception-failures',
    'sourceSystem',
    'eventId',
    'duplicate',
    'undefinedPayloadFields',
    'rawPayload',
    'Security_Event_Ingestion_API_Missing',
]) {
    assert.ok(harnessBody.includes(marker), `Security event harness must keep marker: ${marker}`);
}

for (const marker of [
    'unknown-event-type-001',
    'EVENT_TYPE_NOT_FOUND',
    'missing-base-summary-001',
    'BASE_REQUIRED_FIELD_MISSING',
    'invalid-payload-type-001',
    'PAYLOAD_FIELD_TYPE_INVALID',
    'invalid-payload-enum-001',
    'PAYLOAD_ENUM_VALUE_INVALID',
]) {
    assert.ok(integrationTestBody.includes(marker), `Invalid-config branch marker must stay frozen: ${marker}`);
}

for (const marker of [
    'idempotency_baseline_event',
    'idempotency_conflict_event',
    'failed-idempotency-conflict-001',
    'X-QwenPaw-Test-Persistence-Failure',
    'idempotency_conflict_rejected',
    'failure_records_exist_for_every_failed_branch',
    'persistence_error_submission.event_id',
    'all_failure_summaries_are_bounded',
]) {
    assert.ok(
        integrationTestBody.includes(marker) || harnessBody.includes(marker),
        `Failed-reception branch marker must stay frozen: ${marker}`,
    );
}

for (const marker of [
    'source_filter_returns_only_matching_source',
    'type_filter_returns_only_matching_type',
    'severity_filter_returns_only_matching_severity',
    'time_filter_returns_only_matching_window',
    'event_type_display_name_is_visible',
    'configured_list_payload_field_is_visible',
    'detail_base_facts_are_visible',
    'detail_structured_payload_is_visible',
    'detail_undefined_fields_are_visible',
    'detail_raw_payload_is_visible_and_bounded',
]) {
    assert.ok(harnessBody.includes(marker), `Web inbox observation marker must stay frozen: ${marker}`);
}

for (const marker of [
    'Security Event Ingestion V1',
    'deploy/config/security-event-contracts.v1.json',
    'tests/integration/security/test_security_event_ingestion.py',
    'tests/e2e/security_center/test_security_event_inbox.py',
]) {
    assert.ok(rootContract.includes(marker), `Root contract must reference ${marker}.`);
}

for (const marker of [
    'POST /security-center/v1/events',
    'GET /security-center/v1/operator/events',
    'GET /security-center/v1/operator/events/{sourceSystem}/{eventId}',
    'GET /security-center/v1/operator/event-reception-failures',
    'durably persisted before success',
    'sourceSystem plus eventId',
    'X-QwenPaw-Test-Persistence-Failure',
    'test-environment failure-injection seam',
]) {
    assert.ok(deployApiContract.includes(marker), `deploy/api contract must freeze ${marker}.`);
}

for (const marker of [
    'Security Event Inbox',
    'receivedAt descending',
    'stable detail URLs',
    'source/type/severity/time filter correctness',
    'event type display name',
    'undefined fields',
    'read-only raw payload',
]) {
    assert.ok(deployWebContract.includes(marker), `deploy/web contract must freeze ${marker}.`);
}

for (const marker of [
    'test_security_event_ingestion.py::test_accepts_legal_event_after_persistence',
    'test_security_event_ingestion.py::test_records_failed_receptions_without_business_event_pollution',
    'test_security_event_inbox.py::test_web_lists_filters_and_opens_event_detail',
    'security_event_harness.py',
]) {
    assert.ok(
        testsContract.includes(marker)
        || integrationContract.includes(marker)
        || e2eContract.includes(marker),
        `Test contracts must reference ${marker}.`,
    );
}

assert.ok(
    eventConfig.sourceSystems.some(source => source.sourceSystem === 'endpoint_edr' && source.enabled === true),
    'Config must include enabled endpoint_edr source.',
);
assert.ok(
    eventConfig.sourceSystems.some(source => source.sourceSystem === 'opensandbox' && source.enabled === true),
    'Config must include enabled opensandbox source.',
);
assert.ok(
    eventConfig.sourceSystems.some(source => source.sourceSystem === 'retired_dlp' && source.enabled === false),
    'Config must include disabled retired_dlp source for rejection coverage.',
);
assert.ok(
    eventConfig.eventTypes.some(eventType => eventType.eventTypeId === 'malware_detected'),
    'Config must include malware_detected event type.',
);
assert.ok(
    eventConfig.eventTypes.some(eventType => eventType.eventTypeId === 'opensandbox'),
    'Config must include opensandbox event type.',
);
assert.ok(
    eventConfig.severityValues.includes('DEBUG'),
    'Config must include DEBUG severity for non-anomalous audit events.',
);
assert.ok(
    eventConfig.requestLimits.maxFailureRequestSummaryChars <= 4096,
    'Failure request summaries must be bounded at or below the frozen contract limit.',
);
