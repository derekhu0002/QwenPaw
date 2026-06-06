import React, { useEffect, useMemo, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import dagre from '@dagrejs/dagre';
import htm from 'htm';
import {
  applyNodeChanges,
  Background,
  BackgroundVariant,
  Controls,
  Handle,
  MarkerType,
  MiniMap,
  Position,
  ReactFlow,
  ReactFlowProvider,
} from '@xyflow/react';

const html = htm.bind(React.createElement);
const ROOT_PARENT_ID = '0';
const ALL_VIEWS = '__all__';
const ROOT_MARGIN = 48;
const CONTAINER_PADDING_X = 28;
const CONTAINER_PADDING_Y = 24;
const CONTAINER_HEADER_HEIGHT = 86;
const CONTAINER_MIN_WIDTH = 320;
const CONTAINER_MIN_HEIGHT = 154;
const LEAF_WIDTH = 252;
const LEAF_HEIGHT = 108;
const CONTAINER_COLLAPSED_HEIGHT = 126;

const LEFT_DOCK_MIN_WIDTH = 296;
const LEFT_DOCK_MAX_WIDTH = 460;
const LEFT_DOCK_DEFAULT_WIDTH = 342;
const DRAWER_MIN_WIDTH = 360;
const DRAWER_MAX_WIDTH = 960;
const DRAWER_DEFAULT_WIDTH = 672;

const CHANGE_TONE_NEW = 'new';
const CHANGE_TONE_MODIFIED = 'modified';
const CHANGE_TONE_DELETED = 'deleted';
const EMPTY_CHANGE_SUMMARY = {
  views: { new: [], modified: [], deleted: [] },
  elements: { new: [], modified: [], deleted: [] },
  relationships: { new: [], modified: [], deleted: [] },
  deletedObjects: {
    views: [],
    elements: [],
    relationships: [],
  },
  deletedViewMembership: {
    elements: {},
    relationships: {},
  },
};

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

function isObject(value) {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

function compactText(value, maxLength = 72) {
  if (!value) {
    return '';
  }
  const text = String(value).replace(/\s+/g, ' ').trim();
  return text.length > maxLength ? `${text.slice(0, maxLength - 1)}...` : text;
}

function normalizeText(value) {
  return String(value || '').toLowerCase();
}

function escapeRegex(value) {
  return String(value).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function resolveSchema(schemaRoot, pointerOrSchema) {
  if (!pointerOrSchema) {
    return {};
  }
  if (!pointerOrSchema.$ref) {
    return pointerOrSchema;
  }
  if (!schemaRoot || !pointerOrSchema.$ref.startsWith('#/')) {
    return pointerOrSchema;
  }
  return pointerOrSchema.$ref
    .slice(2)
    .split('/')
    .reduce((current, segment) => current && current[segment], schemaRoot) || pointerOrSchema;
}

function findAttributeValue(attributes, names) {
  const wanted = new Set((names || []).map((name) => String(name).toLowerCase()));
  for (const attribute of attributes || []) {
    if (wanted.has(String(attribute?.name || '').toLowerCase())) {
      return attribute.value || attribute.content || attribute.description || '';
    }
  }
  return '';
}

function deriveStatus(element) {
  const value = (element.status || findAttributeValue(element.attributes, ['health', 'health_status', 'runtime_status', 'state'])).toLowerCase();
  if (!value) {
    return { tone: 'neutral', label: '未知' };
  }
  if (/healthy|running|ok|active|green|ready/.test(value)) {
    return { tone: 'healthy', label: compactText(value, 22) };
  }
  if (/warning|degraded|pending|yellow|paused|warming/.test(value)) {
    return { tone: 'warning', label: compactText(value, 22) };
  }
  if (/error|critical|red|failed|down|blocked/.test(value)) {
    return { tone: 'critical', label: compactText(value, 22) };
  }
  return { tone: 'neutral', label: compactText(value, 22) };
}

function deriveVersion(element) {
  return compactText(findAttributeValue(element.attributes, ['version', 'release', 'build', 'semver']), 24);
}

function normalizeChangeSummary(value) {
  const source = value || {};
  const readGroup = (groupName) => {
    const group = source[groupName] || {};
    return {
      new: new Set((group.new || []).map((id) => String(id))),
      modified: new Set((group.modified || []).map((id) => String(id))),
      deleted: new Set((group.deleted || []).map((id) => String(id))),
    };
  };

  const normalizeArrayById = (items, idField) => {
    const map = new Map();
    for (const item of items || []) {
      const id = item?.[idField];
      if (id !== undefined && id !== null) {
        map.set(String(id), item);
      }
    }
    return map;
  };

  const deletedViewMembership = source.deletedViewMembership || {};

  return {
    views: readGroup('views'),
    elements: readGroup('elements'),
    relationships: readGroup('relationships'),
    deletedObjects: {
      views: normalizeArrayById(source.deletedObjects?.views || [], 'view_id'),
      elements: normalizeArrayById(source.deletedObjects?.elements || [], 'id'),
      relationships: normalizeArrayById(source.deletedObjects?.relationships || [], 'id'),
    },
    deletedViewMembership: {
      elements: new Map(Object.entries(deletedViewMembership.elements || {}).map(([viewId, ids]) => [String(viewId), new Set((ids || []).map((id) => String(id)))])),
      relationships: new Map(Object.entries(deletedViewMembership.relationships || {}).map(([viewId, ids]) => [String(viewId), new Set((ids || []).map((id) => String(id)))])),
    },
  };
}

function pickChangeTone(primaryTone, secondaryTone) {
  if (primaryTone === CHANGE_TONE_NEW || secondaryTone === CHANGE_TONE_NEW) {
    return CHANGE_TONE_NEW;
  }
  if (primaryTone === CHANGE_TONE_MODIFIED || secondaryTone === CHANGE_TONE_MODIFIED) {
    return CHANGE_TONE_MODIFIED;
  }
  if (primaryTone === CHANGE_TONE_DELETED || secondaryTone === CHANGE_TONE_DELETED) {
    return CHANGE_TONE_DELETED;
  }
  return null;
}

function maxChangeTone(tones) {
  let result = null;
  for (const tone of tones || []) {
    result = pickChangeTone(result, tone);
    if (result === CHANGE_TONE_NEW) {
      return result;
    }
  }
  return result;
}

function getChangeTone(changeSummary, kind, id) {
  if (!changeSummary || id === undefined || id === null) {
    return null;
  }
  const key = String(id);
  const group = changeSummary[kind];
  if (!group) {
    return null;
  }
  if (group.new.has(key)) {
    return CHANGE_TONE_NEW;
  }
  if (group.modified.has(key)) {
    return CHANGE_TONE_MODIFIED;
  }
  if (group.deleted.has(key)) {
    return CHANGE_TONE_DELETED;
  }
  return null;
}

function toUniqueStringArray(values) {
  return [...new Set((values || []).map((value) => String(value)))];
}

function buildAugmentedGraph(graph, changeSummary) {
  const next = {
    ...graph,
    elements: [...(graph.elements || [])],
    relationships: [...(graph.relationships || [])],
    views: [...(graph.views || [])],
  };

  const elementById = new Map(next.elements.map((element) => [String(element.id), element]));
  const relationshipById = new Map(next.relationships.map((relationship) => [String(relationship.id), relationship]));
  const viewById = new Map(next.views.map((view) => [String(view.view_id), view]));

  for (const [id, element] of changeSummary.deletedObjects.elements.entries()) {
    if (!elementById.has(id)) {
      next.elements.push(element);
      elementById.set(id, element);
    }
  }

  for (const [id, relationship] of changeSummary.deletedObjects.relationships.entries()) {
    if (!relationshipById.has(id)) {
      next.relationships.push(relationship);
      relationshipById.set(id, relationship);
    }
  }

  for (const [id, view] of changeSummary.deletedObjects.views.entries()) {
    if (!viewById.has(id)) {
      next.views.push(view);
      viewById.set(id, view);
    }
  }

  // Re-attach deleted memberships to current/deleted views so deleted items remain visible until committed.
  next.views = next.views.map((view) => {
    const viewId = String(view.view_id);
    const deletedElements = changeSummary.deletedViewMembership.elements.get(viewId) || new Set();
    const deletedRelationships = changeSummary.deletedViewMembership.relationships.get(viewId) || new Set();
    const includedElements = toUniqueStringArray([...(view.included_elements || []), ...deletedElements]);
    const includedRelationships = toUniqueStringArray([...(view.included_relationships || []), ...deletedRelationships]);
    return {
      ...view,
      included_elements: includedElements,
      included_relationships: includedRelationships,
    };
  });

  // Ensure parent elements know their deleted subdiagram views so hierarchy can still resolve in browser tree.
  const refreshedElementById = new Map(next.elements.map((element) => [String(element.id), element]));
  for (const view of next.views) {
    const parentElementId = view.parent_element_id;
    if (!parentElementId) {
      continue;
    }
    const parentElement = refreshedElementById.get(String(parentElementId));
    if (!parentElement) {
      continue;
    }
    const currentSubviews = parentElement.subdiagram_views || [];
    if (!currentSubviews.some((subview) => String(subview.view_id) === String(view.view_id))) {
      parentElement.subdiagram_views = [...currentSubviews, { view_id: view.view_id, view_name: view.view_name }];
    }
  }

  return next;
}

function deriveElementChangeTone(element, changeSummary) {
  const elementTone = getChangeTone(changeSummary, 'elements', element?.id);
  let viewTone = null;
  for (const subview of element?.subdiagram_views || []) {
    viewTone = pickChangeTone(viewTone, getChangeTone(changeSummary, 'views', subview?.view_id));
    if (viewTone === CHANGE_TONE_NEW) {
      break;
    }
  }
  return pickChangeTone(elementTone, viewTone);
}

function buildCanvasElementChangeMap(indexes, graph, changeSummary) {
  const elementToneMap = new Map();

  function setElementTone(elementId, tone) {
    if (!elementId || !tone) {
      return;
    }
    const key = String(elementId);
    const current = elementToneMap.get(key) || null;
    elementToneMap.set(key, pickChangeTone(current, tone));
  }

  // 1) Direct element changes.
  for (const element of graph.elements || []) {
    const tone = getChangeTone(changeSummary, 'elements', element.id);
    setElementTone(element.id, tone);
  }

  // 2) View changes map to their host elements.
  for (const view of graph.views || []) {
    const tone = getChangeTone(changeSummary, 'views', view.view_id);
    if (tone && view.parent_element_id) {
      setElementTone(view.parent_element_id, tone);
    }
  }

  // 3) Relationship changes map to source/target elements.
  for (const relationship of graph.relationships || []) {
    const tone = getChangeTone(changeSummary, 'relationships', relationship.id);
    if (!tone) {
      continue;
    }
    setElementTone(relationship.source_id || relationship.source, tone);
    setElementTone(relationship.target_id || relationship.target, tone);
  }

  // 4) Propagate tones to ancestor chain until root.
  const seeds = [...elementToneMap.entries()];
  for (const [elementId, tone] of seeds) {
    let parentId = indexes.parentById.get(elementId);
    while (parentId && parentId !== ROOT_PARENT_ID) {
      const current = elementToneMap.get(parentId) || null;
      elementToneMap.set(parentId, pickChangeTone(current, tone));
      parentId = indexes.parentById.get(parentId);
    }
  }

  return elementToneMap;
}

function getPalette(type, isContainer) {
  const normalized = normalizeText(type);
  const defaults = {
    tint: '#b8aa8d',
    border: '#c9bb9e',
    surface: 'linear-gradient(180deg, rgba(255, 248, 233, 0.98), rgba(250, 241, 224, 0.96))',
    accent: '#7e6841',
    shadow: 'rgba(126, 104, 65, 0.12)',
  };

  const palettes = [
    { test: /business|actor|role|process/, value: { tint: '#94b8c8', border: '#9fc3d3', surface: 'linear-gradient(180deg, rgba(234, 244, 249, 0.98), rgba(225, 238, 245, 0.96))', accent: '#4e6b79', shadow: 'rgba(78, 107, 121, 0.12)' } },
    { test: /application|service|function|component|interface/, value: { tint: '#bcaed4', border: '#c5b6de', surface: 'linear-gradient(180deg, rgba(242, 235, 249, 0.98), rgba(233, 224, 244, 0.96))', accent: '#685977', shadow: 'rgba(104, 89, 119, 0.12)' } },
    { test: /technology|node|device|system software|artifact|database/, value: { tint: '#d9c98e', border: '#e0ce8b', surface: 'linear-gradient(180deg, rgba(250, 244, 221, 0.98), rgba(245, 236, 203, 0.96))', accent: '#736335', shadow: 'rgba(115, 99, 53, 0.12)' } },
    { test: /motivation|principle|constraint|assessment|goal|requirement/, value: { tint: '#b8cfab', border: '#c6dbba', surface: 'linear-gradient(180deg, rgba(240, 247, 235, 0.98), rgba(229, 240, 223, 0.96))', accent: '#5d7151', shadow: 'rgba(93, 113, 81, 0.12)' } },
    { test: /implementation|project|work package|deliverable/, value: { tint: '#d9b8a8', border: '#e2c3b5', surface: 'linear-gradient(180deg, rgba(249, 239, 234, 0.98), rgba(244, 228, 220, 0.96))', accent: '#7a5d53', shadow: 'rgba(122, 93, 83, 0.12)' } },
  ];

  const matched = palettes.find((candidate) => candidate.test.test(normalized));
  const palette = matched ? matched.value : defaults;
  if (isContainer) {
    return {
      ...palette,
      surface: `${palette.surface}, radial-gradient(circle at top right, ${palette.border}2a, transparent 42%)`,
    };
  }
  return palette;
}

function classifyRelationship(relationship) {
  const text = normalizeText(`${relationship?.name || ''} ${relationship?.statement || ''} ${relationship?.super_type || ''}`);
  if (/trigger|flow|async|event|message/.test(text)) {
    return { dash: '8 6', width: 1.8, animated: true, label: '异步', color: '#8e835f' };
  }
  if (/realize|implement|serve|composition|aggregation|assignment/.test(text)) {
    return { dash: undefined, width: 2.6, animated: false, label: '强依赖', color: '#7a735f' };
  }
  if (/access|association|used by|read|write/.test(text)) {
    return { dash: '4 5', width: 1.7, animated: false, label: '弱依赖', color: '#8a8376' };
  }
  return { dash: undefined, width: 2.1, animated: false, label: '关联', color: '#6f6758' };
}

function validateGraph(graph, schema) {
  const errors = [];
  const required = schema?.required || [];
  for (const key of required) {
    if (graph?.[key] === undefined) {
      errors.push(`Missing required root field: ${key}`);
    }
  }
  if (!Array.isArray(graph?.elements)) {
    errors.push('elements must be an array');
  }
  if (!Array.isArray(graph?.relationships)) {
    errors.push('relationships must be an array');
  }
  if (!Array.isArray(graph?.views)) {
    errors.push('views must be an array');
  }
  const rootViews = (graph?.views || []).filter((view) => !view.parent_element_id);
  if (rootViews.length !== 1) {
    errors.push(`Expected exactly one structural root view, found ${rootViews.length}`);
  }
  return errors;
}

function resolveStructuralRootView(graph) {
  const rootViews = (graph?.views || []).filter((view) => !view.parent_element_id);
  return rootViews.length === 1 ? rootViews[0] : null;
}

function resolveStructuralRootViews(graph) {
  return (graph?.views || []).filter((view) => !view.parent_element_id);
}

function createIndexes(graph) {
  const elementById = new Map();
  const childrenByParent = new Map();
  const parentById = new Map();
  for (const element of graph.elements || []) {
    elementById.set(element.id, element);
    const parentId = element.parent || ROOT_PARENT_ID;
    parentById.set(element.id, parentId);
    if (!childrenByParent.has(parentId)) {
      childrenByParent.set(parentId, []);
    }
    childrenByParent.get(parentId).push(element.id);
  }
  for (const ids of childrenByParent.values()) {
    ids.sort((left, right) => {
      const leftElement = elementById.get(left);
      const rightElement = elementById.get(right);
      return String(leftElement?.name || left).localeCompare(String(rightElement?.name || right), 'en');
    });
  }
  return {
    elementById,
    childrenByParent,
    parentById,
    viewById: new Map((graph.views || []).map((view) => [view.view_id, view])),
    relationshipById: new Map((graph.relationships || []).map((relationship) => [relationship.id, relationship])),
  };
}

function buildScope(indexes, selectedViewId) {
  if (!selectedViewId || selectedViewId === ALL_VIEWS) {
    return {
      scopeView: null,
      allowedElementIds: new Set(indexes.elementById.keys()),
      allowedRelationshipIds: new Set(indexes.relationshipById.keys()),
    };
  }
  const scopeView = indexes.viewById.get(selectedViewId);
  if (!scopeView) {
    return {
      scopeView: null,
      allowedElementIds: new Set(indexes.elementById.keys()),
      allowedRelationshipIds: new Set(indexes.relationshipById.keys()),
    };
  }

  const allowedElementIds = new Set(scopeView.included_elements || []);

  return {
    scopeView,
    allowedElementIds,
    allowedRelationshipIds: new Set(scopeView.included_relationships || []),
  };
}

function computeInitialCollapsedIds(graph, selectedViewId) {
  if (!graph) {
    return new Set();
  }

  const indexes = createIndexes(graph);
  const scope = buildScope(indexes, selectedViewId);
  const collapsed = new Set();

  for (const elementId of scope.allowedElementIds) {
    const childIds = (indexes.childrenByParent.get(elementId) || []).filter((childId) => scope.allowedElementIds.has(childId));
    if (childIds.length > 0) {
      collapsed.add(elementId);
    }
  }

  return collapsed;
}

function findParentViewId(graph, viewId) {
  if (!graph || !viewId || viewId === ALL_VIEWS) {
    return null;
  }

  const currentView = (graph.views || []).find((view) => view.view_id === viewId);
  if (!currentView?.parent_element_id) {
    return null;
  }

  const parentView = (graph.views || []).find((view) =>
    Array.isArray(view.included_elements) && view.included_elements.includes(currentView.parent_element_id));

  return parentView?.view_id || null;
}

function collectViewPathIds(graph, viewId) {
  if (!graph || !viewId || viewId === ALL_VIEWS) {
    return [];
  }

  const path = [];
  let currentViewId = viewId;
  while (currentViewId) {
    path.unshift(currentViewId);
    currentViewId = findParentViewId(graph, currentViewId);
  }
  return path;
}

function computeExpandedElementIds(graph, viewId, elementId) {
  const collapsed = computeInitialCollapsedIds(graph, viewId);
  const indexes = createIndexes(graph);
  let current = indexes.parentById.get(elementId);
  while (current && current !== ROOT_PARENT_ID) {
    collapsed.delete(current);
    current = indexes.parentById.get(current);
  }
  return collapsed;
}

function buildViewBrowserItems(graph, changeSummary) {
  const rootViews = resolveStructuralRootViews(graph);
  if (rootViews.length === 0) {
    return null;
  }
  const rootViewIds = new Set(rootViews.map((view) => String(view.view_id)));

  const indexes = createIndexes(graph);
  const childViewsByParent = new Map();
  for (const view of graph.views || []) {
    const parentViewId = findParentViewId(graph, view.view_id);
    if (!parentViewId) {
      continue;
    }
    if (!childViewsByParent.has(parentViewId)) {
      childViewsByParent.set(parentViewId, []);
    }
    childViewsByParent.get(parentViewId).push(view);
  }

  for (const siblings of childViewsByParent.values()) {
    siblings.sort((left, right) => String(left.view_name || left.view_id).localeCompare(String(right.view_name || right.view_id), 'en'));
  }

  function buildElementNodes(view) {
    const includedSet = new Set(view.included_elements || []);
    const topLevelIds = [...includedSet].filter((elementId) => {
      const parentId = indexes.parentById.get(elementId);
      return !parentId || parentId === ROOT_PARENT_ID || !includedSet.has(parentId);
    });

    const visitElement = (elementId) => {
      const element = indexes.elementById.get(elementId);
      const childIds = (indexes.childrenByParent.get(elementId) || []).filter((childId) => includedSet.has(childId));
      const childNodes = childIds.map(visitElement);
      const ownTone = getChangeTone(changeSummary, 'elements', elementId);
      const inheritedTone = maxChangeTone(childNodes.map((child) => child.changeTone));
      return {
        kind: 'element',
        key: `element:${elementId}`,
        id: elementId,
        viewId: view.view_id,
        label: element?.name || elementId,
        meta: element?.type || 'element',
        changeTone: pickChangeTone(ownTone, inheritedTone),
        children: childNodes,
      };
    };

    topLevelIds.sort((left, right) => String(indexes.elementById.get(left)?.name || left).localeCompare(String(indexes.elementById.get(right)?.name || right), 'en'));
    return topLevelIds.map(visitElement);
  }

  function buildRelationshipNodes(view) {
    const relationshipIds = [...(view.included_relationships || [])];
    relationshipIds.sort((left, right) => {
      const leftRelationship = indexes.relationshipById.get(left);
      const rightRelationship = indexes.relationshipById.get(right);
      const leftLabel = leftRelationship?.name || leftRelationship?.statement || leftRelationship?.super_type || left;
      const rightLabel = rightRelationship?.name || rightRelationship?.statement || rightRelationship?.super_type || right;
      return String(leftLabel).localeCompare(String(rightLabel), 'en');
    });

    return relationshipIds.map((relationshipId) => {
      const relationship = indexes.relationshipById.get(relationshipId);
      const sourceLabel = indexes.elementById.get(relationship?.source)?.name || relationship?.source || '?';
      const targetLabel = indexes.elementById.get(relationship?.target)?.name || relationship?.target || '?';
      return {
        kind: 'relationship',
        key: `relationship:${relationshipId}`,
        id: relationshipId,
        viewId: view.view_id,
        label: relationship?.name || relationship?.statement || relationship?.super_type || relationshipId,
        meta: `${relationship?.super_type || 'relationship'} · ${sourceLabel} -> ${targetLabel}`,
        changeTone: getChangeTone(changeSummary, 'relationships', relationshipId),
        children: [],
      };
    });
  }

  function visit(view) {
    const childViews = (childViewsByParent.get(view.view_id) || []).map(visit);
    const elementNodes = buildElementNodes(view);
    const relationshipNodes = buildRelationshipNodes(view);
    const inheritedTone = maxChangeTone([...childViews, ...elementNodes, ...relationshipNodes].map((child) => child.changeTone));
    const ownTone = getChangeTone(changeSummary, 'views', view.view_id);
    return {
      kind: 'view',
      key: `view:${view.view_id}`,
      id: view.view_id,
      label: view.view_name,
      meta: `${(view.included_elements || []).length} 个元素 · ${(view.included_relationships || []).length} 条关系`,
      changeTone: pickChangeTone(ownTone, inheritedTone),
      children: [...childViews, ...elementNodes, ...relationshipNodes],
      initiallyExpanded: rootViewIds.has(String(view.view_id)),
    };
  }

  const visited = new Set();
  const rootNodes = [];
  for (const rootView of rootViews) {
    if (visited.has(String(rootView.view_id))) {
      continue;
    }
    const node = visit(rootView);
    visited.add(String(rootView.view_id));
    rootNodes.push(node);
  }

  return {
    kind: 'root',
    key: 'root:system',
    label: graph.name || 'System',
    children: rootNodes,
  };
}

function buildBrowserSearchState(tree, search) {
  const query = normalizeText(search).trim();
  if (!tree || !query) {
    return { matchedKeys: new Set(), expandedKeys: new Set() };
  }

  const matchedKeys = new Set();
  const expandedKeys = new Set(['root:system']);

  function visit(node) {
    const haystack = normalizeText([node.label, node.meta].filter(Boolean).join(' '));
    const selfMatched = haystack.includes(query);
    let descendantMatched = false;

    for (const child of node.children || []) {
      if (visit(child)) {
        descendantMatched = true;
        expandedKeys.add(node.key);
      }
    }

    if (selfMatched) {
      matchedKeys.add(node.key);
    }

    return selfMatched || descendantMatched;
  }

  visit(tree);
  return { matchedKeys, expandedKeys };
}

function TreeNode({ node, depth, expandedIds, matchedKeys, selectedViewId, selectedNodeId, selectedEdgeId, onToggle, onSelectView, onSelectElement, onSelectRelationship }) {
  const isBranch = (node.children || []).length > 0;
  const isExpanded = expandedIds.has(node.key);
  const isView = node.kind === 'view';
  const isRoot = node.kind === 'root';
  const isRelationship = node.kind === 'relationship';
  const isActive = (isView && selectedViewId === node.id)
    || (node.kind === 'element' && selectedNodeId === node.id)
    || (isRelationship && selectedEdgeId === node.id);
  const isMatched = matchedKeys.has(node.key);
  const changeClass = node.changeTone === CHANGE_TONE_NEW
    ? 'is-change-new'
    : node.changeTone === CHANGE_TONE_MODIFIED
      ? 'is-change-modified'
      : node.changeTone === CHANGE_TONE_DELETED
        ? 'is-change-deleted'
      : '';
  const iconClass = isRoot ? 'is-root' : isView ? 'is-view' : isRelationship ? 'is-relationship' : 'is-element';

  return html`
    <div className="tree-node" style=${{ '--tree-depth': depth }}>
      <div className=${`tree-node__row ${isActive ? 'is-active' : ''} ${isMatched ? 'is-match' : ''} ${changeClass}`.trim()}>
        ${isBranch ? html`
          <button
            type="button"
            className="tree-node__toggle"
            aria-label=${isExpanded ? '折叠节点' : '展开节点'}
            onClick=${() => onToggle(node.key)}
          >
            ${isExpanded ? '▾' : '▸'}
          </button>
        ` : html`<span className="tree-node__toggle tree-node__toggle--placeholder"></span>`}
        <button
          type="button"
          className="tree-node__label"
          onClick=${() => {
            if (node.kind === 'view') {
              onSelectView(node.id);
            } else if (node.kind === 'element') {
              onSelectElement(node.viewId, node.id);
            } else if (node.kind === 'relationship') {
              onSelectRelationship(node.viewId, node.id);
            }
          }}
        >
          <span className=${`tree-node__icon ${iconClass}`}></span>
          <span className="tree-node__text">
            <strong>${node.label}</strong>
            ${node.meta ? html`<span>${node.meta}</span>` : null}
          </span>
        </button>
      </div>
      ${isBranch && isExpanded ? html`
        <div className="tree-node__children">
          ${(node.children || []).map((child) => html`
            <${TreeNode}
              key=${child.key}
              node=${child}
              depth=${depth + 1}
              expandedIds=${expandedIds}
              matchedKeys=${matchedKeys}
              selectedViewId=${selectedViewId}
              selectedNodeId=${selectedNodeId}
              selectedEdgeId=${selectedEdgeId}
              onToggle=${onToggle}
              onSelectView=${onSelectView}
              onSelectElement=${onSelectElement}
              onSelectRelationship=${onSelectRelationship}
            />
          `)}
        </div>
      ` : null}
    </div>
  `;
}

function buildMatchSet(indexes, scope, search) {
  const query = normalizeText(search).trim();
  if (!query) {
    return new Set();
  }
  const matches = new Set();
  for (const elementId of scope.allowedElementIds) {
    const element = indexes.elementById.get(elementId);
    const haystack = normalizeText([
      element?.name,
      element?.type,
      element?.alias,
      element?.description,
      element?.status,
      deriveVersion(element),
      ...(element?.attributes || []).map((attribute) => `${attribute.name} ${attribute.description || ''} ${attribute.value || ''} ${attribute.content || ''}`),
    ].join(' '));
    if (haystack.includes(query)) {
      matches.add(elementId);
    }
  }
  return matches;
}

function createDescendantsResolver(indexes, scope) {
  const memo = new Map();
  function resolve(elementId) {
    if (memo.has(elementId)) {
      return memo.get(elementId);
    }
    const descendants = new Set([elementId]);
    for (const childId of indexes.childrenByParent.get(elementId) || []) {
      if (!scope.allowedElementIds.has(childId)) {
        continue;
      }
      for (const descendant of resolve(childId)) {
        descendants.add(descendant);
      }
    }
    memo.set(elementId, descendants);
    return descendants;
  }
  return resolve;
}

function computeForcedOpen(indexes, matchedIds) {
  const forced = new Set();
  for (const elementId of matchedIds) {
    let current = indexes.parentById.get(elementId);
    while (current && current !== ROOT_PARENT_ID) {
      forced.add(current);
      current = indexes.parentById.get(current);
    }
  }
  return forced;
}

function computeHiddenIds(indexes, scope, collapsedSet, forcedOpen) {
  const hidden = new Set();
  const visit = (elementId) => {
    for (const childId of indexes.childrenByParent.get(elementId) || []) {
      if (!scope.allowedElementIds.has(childId)) {
        continue;
      }
      hidden.add(childId);
      visit(childId);
    }
  };

  for (const elementId of collapsedSet) {
    if (!forcedOpen.has(elementId) && scope.allowedElementIds.has(elementId)) {
      visit(elementId);
    }
  }
  return hidden;
}

function resolveVisibleEndpoint(indexes, visibleIds, elementId) {
  let current = elementId;
  while (current && current !== ROOT_PARENT_ID) {
    if (visibleIds.has(current)) {
      return current;
    }
    current = indexes.parentById.get(current);
  }
  return null;
}

function firstBranchUnderParent(indexes, ancestorId, elementId) {
  let current = elementId;
  let previous = null;
  while (current && current !== ROOT_PARENT_ID) {
    const parentId = indexes.parentById.get(current);
    if (parentId === ancestorId) {
      return current;
    }
    previous = current;
    current = parentId;
  }
  return previous;
}

function measureTree(indexes, scope, visibleIds, collapsedSet, layoutDirection) {
  const branchEdgesCache = new Map();

  function buildSiblingEdges(parentId, childIds) {
    const cacheKey = `${parentId}:${childIds.join(',')}`;
    if (branchEdgesCache.has(cacheKey)) {
      return branchEdgesCache.get(cacheKey);
    }
    const childSet = new Set(childIds);
    const edges = [];
    const seen = new Set();
    for (const relationshipId of scope.allowedRelationshipIds) {
      const relationship = indexes.relationshipById.get(relationshipId);
      if (!relationship) {
        continue;
      }
      const sourceBranch = firstBranchUnderParent(indexes, parentId, resolveVisibleEndpoint(indexes, visibleIds, relationship.source_id));
      const targetBranch = firstBranchUnderParent(indexes, parentId, resolveVisibleEndpoint(indexes, visibleIds, relationship.target_id));
      if (!sourceBranch || !targetBranch || sourceBranch === targetBranch || !childSet.has(sourceBranch) || !childSet.has(targetBranch)) {
        continue;
      }
      const key = `${sourceBranch}->${targetBranch}`;
      if (seen.has(key)) {
        continue;
      }
      seen.add(key);
      edges.push({ source: sourceBranch, target: targetBranch });
    }
    branchEdgesCache.set(cacheKey, edges);
    return edges;
  }

  function measureElement(elementId, depth) {
    const childIds = (indexes.childrenByParent.get(elementId) || []).filter((childId) => scope.allowedElementIds.has(childId) && visibleIds.has(childId));
    const collapsed = collapsedSet.has(elementId);
    const hasChildren = childIds.length > 0;

    if (!hasChildren || collapsed) {
      return {
        width: hasChildren ? CONTAINER_MIN_WIDTH : LEAF_WIDTH,
        height: hasChildren ? CONTAINER_COLLAPSED_HEIGHT : LEAF_HEIGHT,
        placements: [],
      };
    }

    const childMeasures = new Map(childIds.map((childId) => [childId, measureElement(childId, depth + 1)]));
    const graph = new dagre.graphlib.Graph();
    graph.setGraph({ rankdir: depth === 0 ? layoutDirection : 'TB', nodesep: 42, ranksep: 72, marginx: 0, marginy: 0 });
    graph.setDefaultEdgeLabel(() => ({}));

    for (const childId of childIds) {
      const childMeasure = childMeasures.get(childId);
      graph.setNode(childId, { width: childMeasure.width, height: childMeasure.height });
    }
    for (const edge of buildSiblingEdges(elementId, childIds)) {
      graph.setEdge(edge.source, edge.target);
    }

    dagre.layout(graph);

    let maxRight = 0;
    let maxBottom = 0;
    const placements = childIds.map((childId) => {
      const node = graph.node(childId);
      const childMeasure = childMeasures.get(childId);
      const x = Math.max(0, node.x - (childMeasure.width / 2));
      const y = Math.max(0, node.y - (childMeasure.height / 2));
      maxRight = Math.max(maxRight, x + childMeasure.width);
      maxBottom = Math.max(maxBottom, y + childMeasure.height);
      return {
        id: childId,
        x,
        y,
        measure: childMeasure,
      };
    });

    return {
      width: Math.max(CONTAINER_MIN_WIDTH, maxRight + (CONTAINER_PADDING_X * 2)),
      height: Math.max(CONTAINER_MIN_HEIGHT, CONTAINER_HEADER_HEIGHT + maxBottom + CONTAINER_PADDING_Y),
      placements,
    };
  }

  const rootIds = [...scope.allowedElementIds].filter((elementId) => {
    if (!visibleIds.has(elementId)) {
      return false;
    }
    const parentId = indexes.parentById.get(elementId);
    return !parentId || parentId === ROOT_PARENT_ID || !scope.allowedElementIds.has(parentId);
  });
  const rootGraph = new dagre.graphlib.Graph();
  rootGraph.setGraph({ rankdir: layoutDirection, nodesep: 56, ranksep: 90, marginx: 0, marginy: 0 });
  rootGraph.setDefaultEdgeLabel(() => ({}));

  const rootMeasures = new Map(rootIds.map((elementId) => [elementId, measureElement(elementId, 0)]));
  for (const elementId of rootIds) {
    const measure = rootMeasures.get(elementId);
    rootGraph.setNode(elementId, { width: measure.width, height: measure.height });
  }

  for (const relationshipId of scope.allowedRelationshipIds) {
    const relationship = indexes.relationshipById.get(relationshipId);
    if (!relationship) {
      continue;
    }
    const source = resolveVisibleEndpoint(indexes, visibleIds, relationship.source_id);
    const target = resolveVisibleEndpoint(indexes, visibleIds, relationship.target_id);
    if (!source || !target || source === target || !rootMeasures.has(source) || !rootMeasures.has(target)) {
      continue;
    }
    rootGraph.setEdge(source, target);
  }

  dagre.layout(rootGraph);

  const layout = new Map();
  let maxRootRight = 0;
  let maxRootBottom = 0;

  function writePlacement(elementId, measure, position, parentId) {
    layout.set(elementId, {
      id: elementId,
      parentId,
      x: position.x,
      y: position.y,
      width: measure.width,
      height: measure.height,
    });
    for (const placement of measure.placements) {
      writePlacement(
        placement.id,
        placement.measure,
        {
          x: placement.x + CONTAINER_PADDING_X,
          y: placement.y + CONTAINER_HEADER_HEIGHT,
        },
        elementId,
      );
    }
  }

  for (const elementId of rootIds) {
    const node = rootGraph.node(elementId);
    const measure = rootMeasures.get(elementId);
    const x = ROOT_MARGIN + node.x - (measure.width / 2);
    const y = ROOT_MARGIN + node.y - (measure.height / 2);
    maxRootRight = Math.max(maxRootRight, x + measure.width);
    maxRootBottom = Math.max(maxRootBottom, y + measure.height);
    writePlacement(elementId, measure, { x, y }, undefined);
  }

  return {
    layout,
    canvasWidth: maxRootRight + ROOT_MARGIN,
    canvasHeight: maxRootBottom + ROOT_MARGIN,
    rootIds,
  };
}

function deriveSelectionGraph(nodes, edges, selected) {
  const directNeighbors = new Set();
  const highlightedEdges = new Set();
  if (!selected || selected.kind !== 'node') {
    return { directNeighbors, highlightedEdges };
  }
  for (const edge of edges) {
    if (edge.source === selected.id || edge.target === selected.id) {
      highlightedEdges.add(edge.id);
      directNeighbors.add(edge.source);
      directNeighbors.add(edge.target);
    }
  }
  return { directNeighbors, highlightedEdges };
}

function EntityNode({ data }) {
  const targetPosition = data.direction === 'LR' ? Position.Left : Position.Top;
  const sourcePosition = data.direction === 'LR' ? Position.Right : Position.Bottom;
  const changeClass = data.changeTone === CHANGE_TONE_NEW
    ? 'is-change-new'
    : data.changeTone === CHANGE_TONE_MODIFIED
      ? 'is-change-modified'
      : data.changeTone === CHANGE_TONE_DELETED
        ? 'is-change-deleted'
      : '';
  return html`
    <div
      className=${`flow-card ${data.variant} ${data.dimmed ? 'is-dimmed' : ''} ${data.highlighted ? 'is-highlighted' : ''} ${data.matched ? 'is-matched' : ''} ${changeClass}`}
      style=${{
        '--node-border': data.palette.border,
        '--node-accent': data.palette.accent,
        '--node-shadow': data.palette.shadow,
        '--node-surface': data.palette.surface,
      }}
      title=${data.tooltip}
    >
      <${Handle} type="target" position=${targetPosition} className="flow-handle" />
      <div className="flow-card__topline">
        <span className="flow-card__type">${data.element.type}</span>
        <span className=${`status-dot status-${data.status.tone}`} title=${data.status.label}></span>
      </div>
      <strong className="flow-card__title">${data.element.name}</strong>
      <div className="flow-card__meta">
        ${data.version ? html`<span className="flow-chip">${data.version}</span>` : null}
        ${data.subviewCount ? html`<span className="flow-chip">${data.subviewCount} 个视图</span>` : null}
      </div>
      ${data.primarySubviewId ? html`
        <div className="flow-action-row">
          <button
            type="button"
            className="node-action nodrag nopan"
            onClick=${(event) => {
              event.stopPropagation();
              data.onOpenSubview(data.primarySubviewId);
            }}
          >
            进入下级视图
          </button>
        </div>
      ` : null}
      <p className="flow-card__copy">${data.description}</p>
      <${Handle} type="source" position=${sourcePosition} className="flow-handle" />
    </div>
  `;
}

function ContainerNode({ data }) {
  const targetPosition = data.direction === 'LR' ? Position.Left : Position.Top;
  const sourcePosition = data.direction === 'LR' ? Position.Right : Position.Bottom;
  const changeClass = data.changeTone === CHANGE_TONE_NEW
    ? 'is-change-new'
    : data.changeTone === CHANGE_TONE_MODIFIED
      ? 'is-change-modified'
      : data.changeTone === CHANGE_TONE_DELETED
        ? 'is-change-deleted'
      : '';
  return html`
    <div
      className=${`flow-card flow-container ${data.dimmed ? 'is-dimmed' : ''} ${data.highlighted ? 'is-highlighted' : ''} ${data.matched ? 'is-matched' : ''} ${changeClass}`}
      style=${{
        '--node-border': data.palette.border,
        '--node-accent': data.palette.accent,
        '--node-shadow': data.palette.shadow,
        '--node-surface': data.palette.surface,
      }}
      title=${data.tooltip}
    >
      <${Handle} type="target" position=${targetPosition} className="flow-handle" />
      <div className="flow-container__header">
        <div>
          <div className="flow-card__topline">
            <span className="flow-card__type">${data.element.type}</span>
            <span className=${`status-dot status-${data.status.tone}`} title=${data.status.label}></span>
          </div>
          <strong className="flow-card__title">${data.element.name}</strong>
          <div className="flow-card__meta">
            <span className="flow-chip">${data.childCount} 个子节点</span>
            ${data.version ? html`<span className="flow-chip">${data.version}</span>` : null}
          </div>
        </div>
        <button
          type="button"
          className="collapse-button nodrag nopan"
          onClick=${(event) => {
            event.stopPropagation();
            data.onToggleCollapse(data.element.id);
          }}
        >
          ${data.collapsed ? '展开' : '收起'}
        </button>
      </div>
      <p className="flow-card__copy">${data.description}</p>
      ${data.primarySubviewId ? html`
        <div className="flow-action-row">
          <button
            type="button"
            className="node-action nodrag nopan"
            onClick=${(event) => {
              event.stopPropagation();
              data.onOpenSubview(data.primarySubviewId);
            }}
          >
            进入下级视图
          </button>
        </div>
      ` : null}
      <div className="flow-container__hint">${data.collapsed ? '已隐藏子节点以简化当前视图。' : '嵌套节点会随父容器一起拖拽。'}</div>
      <${Handle} type="source" position=${sourcePosition} className="flow-handle" />
    </div>
  `;
}

const nodeTypes = {
  entity: EntityNode,
  container: ContainerNode,
};

function buildFlowModel(graph, schema, selectedViewId, search, collapsedSet, layoutDirection, onToggleCollapse, onOpenSubview, selected, positionOverrides, changeSummary) {
  const indexes = createIndexes(graph);
  const elementChangeMap = buildCanvasElementChangeMap(indexes, graph, changeSummary);
  const scope = buildScope(indexes, selectedViewId);
  const matchedIds = buildMatchSet(indexes, scope, search);
  const forcedOpen = computeForcedOpen(indexes, matchedIds);
  const effectiveCollapsed = new Set([...collapsedSet].filter((elementId) => !forcedOpen.has(elementId)));
  const hiddenIds = computeHiddenIds(indexes, scope, effectiveCollapsed, forcedOpen);
  const visibleIds = new Set([...scope.allowedElementIds].filter((elementId) => !hiddenIds.has(elementId)));
  const layout = measureTree(indexes, scope, visibleIds, effectiveCollapsed, layoutDirection);
  const nodeDrafts = [];

  for (const [elementId, placement] of layout.layout.entries()) {
    const element = indexes.elementById.get(elementId);
    const childCount = (indexes.childrenByParent.get(elementId) || []).filter((childId) => scope.allowedElementIds.has(childId)).length;
    const hasChildren = childCount > 0;
    const palette = getPalette(element.type, hasChildren);
    const status = deriveStatus(element);
    const matched = matchedIds.has(elementId);
    const tooltip = [element.name, element.type, element.description].filter(Boolean).join(' | ');
    const changeTone = elementChangeMap.get(String(elementId)) || deriveElementChangeTone(element, changeSummary);

    nodeDrafts.push({
      id: elementId,
      type: hasChildren ? 'container' : 'entity',
      position: positionOverrides.get(elementId) || { x: placement.x, y: placement.y },
      parentId: placement.parentId,
      extent: placement.parentId ? 'parent' : undefined,
      draggable: true,
      dragHandle: '.flow-card',
      style: { width: placement.width, height: placement.height },
      data: {
        element,
        variant: hasChildren ? 'container' : 'entity',
        childCount,
        collapsed: effectiveCollapsed.has(elementId),
        description: compactText(element.description || '暂无描述。', hasChildren ? 140 : 92),
        direction: layoutDirection,
        dimmed: false,
        highlighted: false,
        matched,
        changeTone,
        onOpenSubview,
        onToggleCollapse,
        palette,
        primarySubviewId: element.subdiagram_views?.[0]?.view_id || null,
        status,
        subviewCount: (element.subdiagram_views || []).length,
        tooltip,
        version: deriveVersion(element),
      },
    });
  }

  const edgeDrafts = [];
  const edgeKeys = new Set();
  for (const relationshipId of scope.allowedRelationshipIds) {
    const relationship = indexes.relationshipById.get(relationshipId);
    if (!relationship) {
      continue;
    }
    const source = resolveVisibleEndpoint(indexes, visibleIds, relationship.source_id);
    const target = resolveVisibleEndpoint(indexes, visibleIds, relationship.target_id);
    if (!source || !target || source === target) {
      continue;
    }
    const dedupeKey = `${source}:${target}:${relationship.name || relationship.statement || relationship.id}`;
    if (edgeKeys.has(dedupeKey)) {
      continue;
    }
    edgeKeys.add(dedupeKey);
    const styleToken = classifyRelationship(relationship);
    const changeTone = getChangeTone(changeSummary, 'relationships', relationship.id);
    edgeDrafts.push({
      id: relationship.id,
      source,
      target,
      type: 'smoothstep',
      animated: styleToken.animated,
      label: compactText(relationship.name || relationship.statement || styleToken.label, 28),
      labelBgPadding: [7, 4],
      labelBgBorderRadius: 999,
      labelBgStyle: { fill: '#fffaf1', fillOpacity: 0.96 },
      markerEnd: { type: MarkerType.ArrowClosed, color: styleToken.color },
      style: {
        stroke: styleToken.color,
        strokeDasharray: styleToken.dash,
        strokeWidth: styleToken.width,
      },
      data: {
        relationship,
        changeTone,
        dimmed: false,
        highlighted: false,
      },
    });
  }

  const selectionGraph = deriveSelectionGraph(nodeDrafts, edgeDrafts, selected);
  const relatedIds = new Set(selectionGraph.directNeighbors);
  if (selected?.kind === 'node') {
    relatedIds.add(selected.id);
  }

  const nodes = nodeDrafts.map((node) => ({
    ...node,
    className: `${node.className || ''} ${selected?.kind === 'node' && selected.id !== node.id && !relatedIds.has(node.id) ? 'node-dimmed' : ''}`.trim(),
    data: {
      ...node.data,
      dimmed: selected?.kind === 'node' && selected.id !== node.id && !relatedIds.has(node.id),
      highlighted: selected?.kind === 'node' && relatedIds.has(node.id),
    },
  }));

  const edges = edgeDrafts.map((edge) => ({
    ...edge,
    className: `${selected?.kind === 'node' && !selectionGraph.highlightedEdges.has(edge.id) ? 'edge-dimmed' : ''} ${selectionGraph.highlightedEdges.has(edge.id) ? 'edge-highlighted' : ''} ${edge.data.changeTone === CHANGE_TONE_NEW ? 'edge-change-new' : ''} ${edge.data.changeTone === CHANGE_TONE_MODIFIED ? 'edge-change-modified' : ''} ${edge.data.changeTone === CHANGE_TONE_DELETED ? 'edge-change-deleted' : ''}`.trim(),
    data: {
      ...edge.data,
      dimmed: selected?.kind === 'node' && !selectionGraph.highlightedEdges.has(edge.id),
      highlighted: selectionGraph.highlightedEdges.has(edge.id),
    },
  }));

  return {
    nodes,
    edges,
    indexes,
    scope,
    matchedIds,
    metrics: {
      totalElements: scope.allowedElementIds.size,
      visibleElements: nodes.length,
      relationships: edges.length,
      views: graph.views?.length || 0,
    },
    canvasSize: {
      width: layout.canvasWidth,
      height: layout.canvasHeight,
    },
  };
}

function formatStructuredValue(value) {
  if (value === null || value === undefined || value === '') {
    return '---';
  }
  if (typeof value === 'boolean') {
    return value ? 'true' : 'false';
  }
  return String(value);
}

const DETAIL_HIDDEN_FIELDS = new Set(['subdiagram_views']);

function shouldDisplayDetailField(key, value) {
  if (DETAIL_HIDDEN_FIELDS.has(key)) {
    return false;
  }
  if (key === 'parent' && (value === undefined || value === null || value === '')) {
    return false;
  }
  return true;
}

function formatFlatStructuredValue(value) {
  if (value === null || value === undefined || value === '') {
    return '---';
  }
  if (typeof value === 'boolean') {
    return value ? 'true' : 'false';
  }
  if (typeof value === 'object') {
    try {
      return JSON.stringify(value);
    } catch {
      return String(value);
    }
  }
  return String(value);
}

function flattenArrayRows(fieldKey, items) {
  if (!Array.isArray(items) || items.length === 0) {
    return [{ label: fieldKey, value: '---', flattened: true }];
  }

  const rows = [];
  items.forEach((entry, index) => {
    const baseLabel = `${fieldKey}[${index}]`;
    if (entry && typeof entry === 'object' && !Array.isArray(entry)) {
      const nestedEntries = Object.entries(entry).filter(([key, nestedValue]) => shouldDisplayDetailField(key, nestedValue));
      if (nestedEntries.length === 0) {
        rows.push({ label: baseLabel, value: '---', flattened: true });
        return;
      }
      nestedEntries.forEach(([nestedKey, nestedValue]) => {
        rows.push({ label: `${baseLabel}.${nestedKey}`, value: nestedValue, flattened: true });
      });
      return;
    }
    rows.push({ label: baseLabel, value: entry, flattened: true });
  });

  return rows;
}

function StructuredValueTable({ value, depth = 0 }) {
  if (Array.isArray(value)) {
    if (value.length === 0) {
      return html`<span className="structured-value structured-value--empty">---</span>`;
    }

    const rows = flattenArrayRows('item', value);

    return html`
      <div className=${`structured-table-wrap${depth > 0 ? ' is-nested' : ''}`}>
        <table className="structured-table">
          <tbody>
            ${rows.map((row, index) => html`
              <tr key=${`${row.label}-${index}`}>
                <th>${row.label}</th>
                <td>
                  <span className="structured-value">${formatFlatStructuredValue(row.value)}</span>
                </td>
              </tr>
            `)}
          </tbody>
        </table>
      </div>
    `;
  }

  if (value && typeof value === 'object') {
    const entries = Object.entries(value).filter(([key, entryValue]) => shouldDisplayDetailField(key, entryValue));
    if (entries.length === 0) {
      return html`<span className="structured-value structured-value--empty">---</span>`;
    }

    const rows = entries.flatMap(([key, entryValue]) => {
      if (Array.isArray(entryValue)) {
        return flattenArrayRows(key, entryValue);
      }
      return [{ label: key, value: entryValue, flattened: false }];
    });

    return html`
      <div className=${`structured-table-wrap${depth > 0 ? ' is-nested' : ''}`}>
        <table className="structured-table">
          <tbody>
            ${rows.map((row, index) => html`
              <tr key=${`${row.label}-${index}`}>
                <th>${row.label}</th>
                <td>
                  ${!row.flattened && typeof row.value === 'object' && row.value !== null
                    ? html`<${StructuredValueTable} value=${row.value} depth=${depth + 1} />`
                    : html`<span className="structured-value">${row.flattened ? formatFlatStructuredValue(row.value) : formatStructuredValue(row.value)}</span>`}
                </td>
              </tr>
            `)}
          </tbody>
        </table>
      </div>
    `;
  }

  return html`<span className="structured-value">${formatStructuredValue(value)}</span>`;
}

function DetailsDrawer({ selection, flowModel, schema, anchorRef }) {
  const drawerRef = useRef(null);
  const drawerHeadRef = useRef(null);
  const drawerResizeHandleRef = useRef(null);
  const [drawerPosition, setDrawerPosition] = useState(null);
  const [drawerDrag, setDrawerDrag] = useState(false);
  const [drawerResize, setDrawerResize] = useState(false);
  const [drawerCollapsed, setDrawerCollapsed] = useState(false);
  const [drawerWidth, setDrawerWidth] = useState(DRAWER_DEFAULT_WIDTH);

  const clampDrawerWidth = (nextWidth, rightEdge = null) => {
    const anchor = anchorRef?.current;
    if (!anchor) {
      return clamp(nextWidth, DRAWER_MIN_WIDTH, DRAWER_MAX_WIDTH);
    }

    const anchorRect = anchor.getBoundingClientRect();
    const widthByAnchor = anchorRect.width - 24;
    const widthByEdge = rightEdge === null ? widthByAnchor : rightEdge - 12;
    const maxWidth = Math.max(DRAWER_MIN_WIDTH, Math.min(DRAWER_MAX_WIDTH, widthByAnchor, widthByEdge));
    return clamp(nextWidth, DRAWER_MIN_WIDTH, maxWidth);
  };

  const clampDrawerPosition = (nextPosition, widthOverride = drawerWidth) => {
    const anchor = anchorRef?.current;
    const drawer = drawerRef.current;
    if (!anchor || !drawer || !nextPosition) {
      return nextPosition;
    }

    const anchorRect = anchor.getBoundingClientRect();
    const drawerRect = drawer.getBoundingClientRect();
    const maxLeft = Math.max(12, anchorRect.width - widthOverride - 12);
    const maxTop = Math.max(12, anchorRect.height - drawerRect.height - 12);
    return {
      left: clamp(nextPosition.left, 12, maxLeft),
      top: clamp(nextPosition.top, 12, maxTop),
    };
  };

  useEffect(() => {
    const handleResize = () => {
      const nextWidth = clampDrawerWidth(
        drawerWidth,
        drawerPosition ? drawerPosition.left + drawerWidth : null,
      );
      if (nextWidth !== drawerWidth) {
        setDrawerWidth(nextWidth);
      }
      setDrawerPosition((current) => clampDrawerPosition(current, nextWidth));
    };

    window.addEventListener('resize', handleResize);
    return () => {
      window.removeEventListener('resize', handleResize);
    };
  }, [anchorRef, drawerPosition, drawerWidth]);

  const startDrawerDrag = (event) => {
    if (window.innerWidth <= 1080 || !drawerRef.current || !anchorRef?.current) {
      return;
    }

    event.preventDefault();

    const drawerRect = drawerRef.current.getBoundingClientRect();
    const anchorRect = anchorRef.current.getBoundingClientRect();
    const initialPosition = clampDrawerPosition({
      left: drawerRect.left - anchorRect.left,
      top: drawerRect.top - anchorRect.top,
    });

    drawerRef.current.style.left = `${initialPosition.left}px`;
    drawerRef.current.style.top = `${initialPosition.top}px`;
    drawerRef.current.style.right = 'auto';
    setDrawerPosition(initialPosition);
    setDrawerDrag(true);

    const handleDragMove = (moveEvent) => {
      const nextPosition = clampDrawerPosition({
        left: initialPosition.left + (moveEvent.clientX - event.clientX),
        top: initialPosition.top + (moveEvent.clientY - event.clientY),
      });

      if (drawerRef.current) {
        drawerRef.current.style.left = `${nextPosition.left}px`;
        drawerRef.current.style.top = `${nextPosition.top}px`;
        drawerRef.current.style.right = 'auto';
      }
      setDrawerPosition(nextPosition);
    };

    const handleDragEnd = () => {
      setDrawerDrag(false);
      window.removeEventListener('mousemove', handleDragMove);
      window.removeEventListener('mouseup', handleDragEnd);
    };

    window.addEventListener('mousemove', handleDragMove);
    window.addEventListener('mouseup', handleDragEnd);
  };

  const startDrawerResize = (event) => {
    if (window.innerWidth <= 1080 || !drawerRef.current || !anchorRef?.current) {
      return;
    }

    event.preventDefault();
    event.stopPropagation();

    const drawerRect = drawerRef.current.getBoundingClientRect();
    const anchorRect = anchorRef.current.getBoundingClientRect();
    const initialPosition = drawerPosition || {
      left: drawerRect.left - anchorRect.left,
      top: drawerRect.top - anchorRect.top,
    };
    const rightEdge = initialPosition.left + drawerRect.width;
    const initialWidth = drawerRect.width;

    setDrawerResize(true);

    const handleResizeMove = (moveEvent) => {
      const proposedWidth = initialWidth - (moveEvent.clientX - event.clientX);
      const nextWidth = clampDrawerWidth(proposedWidth, rightEdge);

      if (drawerRef.current) {
        drawerRef.current.style.width = `${nextWidth}px`;
      }

      if (drawerPosition) {
        const nextPosition = clampDrawerPosition({
          left: rightEdge - nextWidth,
          top: initialPosition.top,
        }, nextWidth);

        if (drawerRef.current) {
          drawerRef.current.style.left = `${nextPosition.left}px`;
          drawerRef.current.style.top = `${nextPosition.top}px`;
          drawerRef.current.style.right = 'auto';
        }

        setDrawerPosition(nextPosition);
      }

      setDrawerWidth(nextWidth);
    };

    const handleResizeEnd = () => {
      setDrawerResize(false);
      window.removeEventListener('mousemove', handleResizeMove);
      window.removeEventListener('mouseup', handleResizeEnd);
    };

    window.addEventListener('mousemove', handleResizeMove);
    window.addEventListener('mouseup', handleResizeEnd);
  };

  useEffect(() => {
    const drawerHead = drawerHeadRef.current;
    if (!drawerHead) {
      return undefined;
    }

    const handleMouseDown = (event) => {
      if (event.target instanceof Element && event.target.closest('.drawer-collapse')) {
        return;
      }
      if (event.target instanceof Element && event.target.closest('.drawer-grip')) {
        event.preventDefault();
      }
      startDrawerDrag(event);
    };

    drawerHead.addEventListener('mousedown', handleMouseDown);
    return () => drawerHead.removeEventListener('mousedown', handleMouseDown);
  }, [anchorRef, selection]);

  useEffect(() => {
    const resizeHandle = drawerResizeHandleRef.current;
    if (!resizeHandle) {
      return undefined;
    }

    resizeHandle.addEventListener('mousedown', startDrawerResize);
    return () => resizeHandle.removeEventListener('mousedown', startDrawerResize);
  }, [anchorRef, selection, drawerPosition, drawerWidth]);

  const drawerPositionStyle = drawerPosition
    ? { left: `${drawerPosition.left}px`, top: `${drawerPosition.top}px`, right: 'auto' }
    : undefined;

  const drawerStyle = drawerPositionStyle || undefined;

  const reopenDrawer = () => {
    setDrawerCollapsed(false);
  };

  const selectedObject = useMemo(() => {
    if (!selection) {
      return null;
    }
    if (selection.kind === 'node') {
      return {
        kind: '元素',
        value: flowModel.indexes.elementById.get(selection.id),
        schema: resolveSchema(schema, schema?.$defs?.element),
      };
    }
    if (selection.kind === 'edge') {
      return {
        kind: '关系',
        value: flowModel.indexes.relationshipById.get(selection.id),
        schema: resolveSchema(schema, schema?.$defs?.relationship),
      };
    }
    return null;
  }, [flowModel, schema, selection]);

  if (drawerCollapsed) {
    return html`
      <button
        type="button"
        className="drawer-collapsed-toggle"
        style=${drawerPositionStyle}
        onClick=${reopenDrawer}
        aria-label="重新展开详情抽屉"
      >
        <span className="drawer-collapsed-toggle__icon">◀</span>
        <span>展开详情</span>
      </button>
    `;
  }

  if (!selectedObject?.value) {
    return html`
      <aside ref=${drawerRef} className=${`drawer panel${drawerDrag ? ' is-dragging' : ''}${drawerResize ? ' is-resizing' : ''}`} style=${drawerStyle}>
        <div ref=${drawerHeadRef} className="drawer-head">
          <div className="drawer-head__title">
            <span className="eyebrow eyebrow-inline">详情</span>
            <h3>详情抽屉</h3>
          </div>
          <div className="drawer-head__actions">
            <button
              type="button"
              className="drawer-collapse"
              aria-label="收起详情抽屉"
              onMouseDown=${(event) => {
                event.stopPropagation();
              }}
              onClick=${(event) => {
                event.stopPropagation();
                setDrawerCollapsed(true);
              }}
            >
              —
            </button>
            <button type="button" className="drawer-grip" aria-label="拖动详情抽屉">:::</button>
          </div>
        </div>
        <div className="drawer-empty">
          <p>选择一个节点或关系后，可在这里查看结构化字段详情。</p>
        </div>
      </aside>
    `;
  }

  const requiredFields = selectedObject.schema?.required || [];
  const presentFields = Object.keys(selectedObject.value || {});
  const missingFields = requiredFields.filter((field) => selectedObject.value[field] === undefined);

  return html`
    <aside ref=${drawerRef} className=${`drawer panel${drawerDrag ? ' is-dragging' : ''}${drawerResize ? ' is-resizing' : ''}`} style=${drawerStyle}>
      <div ref=${drawerHeadRef} className="drawer-head">
        <div className="drawer-head__title">
          <span className="eyebrow eyebrow-inline">${selectedObject.kind}</span>
          <h3>${selectedObject.value.name || selectedObject.value.statement || selectedObject.value.view_name || selectedObject.value.id}</h3>
        </div>
        <div className="drawer-head__actions">
          <button
            type="button"
            className="drawer-collapse"
            aria-label="收起详情抽屉"
            onMouseDown=${(event) => {
              event.stopPropagation();
            }}
            onClick=${(event) => {
              event.stopPropagation();
              setDrawerCollapsed(true);
            }}
          >
            —
          </button>
          <button type="button" className="drawer-grip" aria-label="拖动详情抽屉">:::</button>
        </div>
      </div>
      <div className="drawer-section drawer-scrollable">
        <h4>结构化详情</h4>
        <${StructuredValueTable} value=${selectedObject.value} />
      </div>
    </aside>
  `;
}

function ViewBrowser({ tree, expandedIds, matchedKeys, selectedViewId, selectedNodeId, selectedEdgeId, onToggle, onSelectView, onSelectElement, onSelectRelationship }) {
  if (!tree) {
    return html`
      <section className="sidebar-section sidebar-browser">
        <div className="tree-browser tree-scroll">
          <div className="tree-empty">当前没有可展示的结构化视图。</div>
        </div>
      </section>
    `;
  }

  return html`
    <section className="sidebar-section sidebar-browser">
      <div className="tree-browser tree-scroll">
        <${TreeNode}
          node=${tree}
          depth=${0}
          expandedIds=${expandedIds}
          matchedKeys=${matchedKeys}
          selectedViewId=${selectedViewId}
          selectedNodeId=${selectedNodeId}
          selectedEdgeId=${selectedEdgeId}
          onToggle=${onToggle}
          onSelectView=${onSelectView}
          onSelectElement=${onSelectElement}
          onSelectRelationship=${onSelectRelationship}
        />
      </div>
    </section>
  `;
}

function GraphCanvas({ flowModel, selection, setSelection, layoutDirection, onNodeDragStop }) {
  const flowRef = useRef(null);
  const canvasHeight = Math.max(780, Math.min(1320, flowModel.canvasSize.height + 120));
  const [renderNodes, setRenderNodes] = useState(flowModel.nodes);

  useEffect(() => {
    setRenderNodes(flowModel.nodes);
  }, [flowModel.nodes]);

  const handleCanvasNodesChange = (changes) => {
    setRenderNodes((current) => applyNodeChanges(changes, current));
  };

  useEffect(() => {
    if (!flowRef.current) {
      return;
    }
    const timer = window.setTimeout(() => {
      flowRef.current.fitView({ duration: 480, padding: 0.16, includeHiddenNodes: false });
    }, 60);
    return () => window.clearTimeout(timer);
  }, [flowModel.edges, flowModel.nodes, layoutDirection]);

  return html`
    <div className="canvas panel">
      <div className="canvas-head">
        <div>
          <span className="eyebrow eyebrow-inline">画布</span>
          <h2>架构地图</h2>
          <p>拖拽节点、切换视图，并在右侧查看对象详情。</p>
        </div>
        <div className="canvas-metrics">
          <span className="pill">${flowModel.metrics.visibleElements} 个可见节点</span>
          <span className="pill">${flowModel.metrics.relationships} 条关系连线</span>
        </div>
      </div>
      <div className="canvas-frame" style=${{ height: `${canvasHeight}px`, minHeight: `${canvasHeight}px` }}>
        <${ReactFlow}
          nodes=${renderNodes}
          edges=${flowModel.edges}
          nodeTypes=${nodeTypes}
          onNodesChange=${handleCanvasNodesChange}
          onInit=${(instance) => {
            flowRef.current = instance;
          }}
          onNodeDragStop=${(_event, node) => onNodeDragStop(node)}
          onNodeClick=${(_event, node) => setSelection({ kind: 'node', id: node.id })}
          onEdgeClick=${(_event, edge) => setSelection({ kind: 'edge', id: edge.id })}
          onPaneClick=${() => setSelection(null)}
          fitView=${true}
          minZoom=${0.2}
          maxZoom=${1.8}
          defaultEdgeOptions=${{ zIndex: 3 }}
          nodesDraggable=${true}
          elementsSelectable=${true}
          proOptions=${{ hideAttribution: true }}
          colorMode="light"
        >
          <${MiniMap}
            pannable=${true}
            zoomable=${true}
            nodeColor=${(node) => node?.data?.palette?.border || '#94a3b8'}
            maskColor="rgba(248, 243, 233, 0.72)"
            className="flow-minimap"
          />
          <${Controls} className="flow-controls" showInteractive=${false} />
          <${Background} variant=${BackgroundVariant.Dots} gap=${22} size=${1.1} color="#d8cfbd" />
        </${ReactFlow}>
      </div>
    </div>
  `;
}

function App() {
  const leftDockRef = useRef(null);
  const workspaceDividerRef = useRef(null);
  const stageShellRef = useRef(null);
  const [schema, setSchema] = useState(null);
  const [graph, setGraph] = useState(null);
  const [validationErrors, setValidationErrors] = useState([]);
  const [search, setSearch] = useState('');
  const [selectedViewId, setSelectedViewId] = useState(ALL_VIEWS);
  const [collapsedIds, setCollapsedIds] = useState(new Set());
  const [layoutDirection, setLayoutDirection] = useState('LR');
  const [selection, setSelection] = useState(null);
  const [loadingError, setLoadingError] = useState('');
  const [positionOverrides, setPositionOverrides] = useState(new Map());
  const [changeSummary, setChangeSummary] = useState(() => normalizeChangeSummary(EMPTY_CHANGE_SUMMARY));
  const [expandedBrowserIds, setExpandedBrowserIds] = useState(new Set(['root:system']));
  const [leftDockWidth, setLeftDockWidth] = useState(LEFT_DOCK_DEFAULT_WIDTH);
  const [leftDockResizing, setLeftDockResizing] = useState(false);
  const [isCompactLayout, setIsCompactLayout] = useState(() => window.innerWidth <= 1080);

  useEffect(() => {
    async function load() {
      try {
        const [schemaResponse, dataResponse, changesResponse] = await Promise.all([
          fetch('/api/schema'),
          fetch('/api/data'),
          fetch('/api/changes'),
        ]);
        if (!schemaResponse.ok) {
          throw new Error(`Schema request failed: ${schemaResponse.status}`);
        }
        if (!dataResponse.ok) {
          throw new Error(`Data request failed: ${dataResponse.status}`);
        }
        const [schemaJson, graphJson, changeJson] = await Promise.all([
          schemaResponse.json(),
          dataResponse.json(),
          changesResponse.ok ? changesResponse.json() : Promise.resolve(EMPTY_CHANGE_SUMMARY),
        ]);
        const structuralRoot = resolveStructuralRootView(graphJson);
        setSchema(schemaJson);
        setGraph(graphJson);
        setChangeSummary(normalizeChangeSummary(changeJson));
        setValidationErrors(validateGraph(graphJson, schemaJson));
        if (structuralRoot?.view_id) {
          setSelectedViewId(structuralRoot.view_id);
          setCollapsedIds(computeInitialCollapsedIds(graphJson, structuralRoot.view_id));
          setExpandedBrowserIds(new Set(['root:system', ...collectViewPathIds(graphJson, structuralRoot.view_id).map((viewId) => `view:${viewId}`)]));
        } else {
          setSelectedViewId(ALL_VIEWS);
          setCollapsedIds(computeInitialCollapsedIds(graphJson, ALL_VIEWS));
          setExpandedBrowserIds(new Set(['root:system']));
        }
        setPositionOverrides(new Map());
      } catch (error) {
        setLoadingError(error instanceof Error ? error.message : String(error));
      }
    }
    load();
  }, []);

  const toggleCollapse = (elementId) => {
    setCollapsedIds((current) => {
      const next = new Set(current);
      if (next.has(elementId)) {
        next.delete(elementId);
      } else {
        next.add(elementId);
      }
      return next;
    });
  };

  const openSubview = (nextViewId) => {
    if (!nextViewId) {
      return;
    }
    setSelectedViewId(nextViewId);
    setExpandedBrowserIds((current) => new Set([...current, ...collectViewPathIds(effectiveGraph || graph, nextViewId).map((viewId) => `view:${viewId}`)]));
    setCollapsedIds(computeInitialCollapsedIds(effectiveGraph || graph, nextViewId));
    setPositionOverrides(new Map());
    setSelection(null);
  };

  const openElementFromBrowser = (viewId, elementId) => {
    if (!viewId || !elementId) {
      return;
    }
    setSelectedViewId(viewId);
    setExpandedBrowserIds((current) => new Set([...current, ...collectViewPathIds(effectiveGraph || graph, viewId).map((nextViewId) => `view:${nextViewId}`)]));
    setCollapsedIds(computeExpandedElementIds(effectiveGraph || graph, viewId, elementId));
    setPositionOverrides(new Map());
    setSelection({ kind: 'node', id: elementId });
  };

  const openRelationshipFromBrowser = (viewId, relationshipId) => {
    if (!viewId || !relationshipId) {
      return;
    }
    setSelectedViewId(viewId);
    setExpandedBrowserIds((current) => new Set([...current, ...collectViewPathIds(effectiveGraph || graph, viewId).map((nextViewId) => `view:${nextViewId}`)]));
    setCollapsedIds(computeInitialCollapsedIds(effectiveGraph || graph, viewId));
    setPositionOverrides(new Map());
    setSelection({ kind: 'edge', id: relationshipId });
  };

  const toggleBrowserNode = (nodeKey) => {
    setExpandedBrowserIds((current) => {
      const next = new Set(current);
      if (next.has(nodeKey)) {
        next.delete(nodeKey);
      } else {
        next.add(nodeKey);
      }
      return next;
    });
  };

  const handleNodeDragStop = (node) => {
    setPositionOverrides((current) => {
      const next = new Map(current);
      if (node?.id && node.position) {
        next.set(node.id, node.position);
      }
      return next;
    });
  };

  useEffect(() => {
    setPositionOverrides(new Map());
  }, [selectedViewId, collapsedIds, layoutDirection, search]);

  useEffect(() => {
    const handleResize = () => {
      setIsCompactLayout(window.innerWidth <= 1080);
      setLeftDockWidth((current) => clamp(current, LEFT_DOCK_MIN_WIDTH, LEFT_DOCK_MAX_WIDTH));
    };

    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  const startLeftDockResize = (event) => {
    if (isCompactLayout) {
      return;
    }

    event.preventDefault();
    const startClientX = event.clientX;
    const initialWidth = leftDockWidth;
    setLeftDockResizing(true);

    const handleMove = (moveEvent) => {
      const nextWidth = clamp(initialWidth + (moveEvent.clientX - startClientX), LEFT_DOCK_MIN_WIDTH, LEFT_DOCK_MAX_WIDTH);
      setLeftDockWidth(nextWidth);
    };

    const handleUp = () => {
      setLeftDockResizing(false);
      window.removeEventListener('mousemove', handleMove);
      window.removeEventListener('mouseup', handleUp);
    };

    window.addEventListener('mousemove', handleMove);
    window.addEventListener('mouseup', handleUp);
  };

  const bindWorkspaceDividerRef = (node) => {
    workspaceDividerRef.current = node;
    if (node) {
      node.onmousedown = isCompactLayout ? null : startLeftDockResize;
      node.onpointerdown = isCompactLayout ? null : startLeftDockResize;
    }
  };

  const effectiveGraph = useMemo(() => {
    if (!graph) {
      return null;
    }
    return buildAugmentedGraph(graph, changeSummary);
  }, [changeSummary, graph]);

  const flowModel = useMemo(() => {
    if (!effectiveGraph || !schema) {
      return null;
    }
    return buildFlowModel(effectiveGraph, schema, selectedViewId, search, collapsedIds, layoutDirection, toggleCollapse, openSubview, selection, positionOverrides, changeSummary);
  }, [changeSummary, collapsedIds, effectiveGraph, layoutDirection, positionOverrides, schema, search, selectedViewId, selection]);

  const browserTree = useMemo(() => (effectiveGraph ? buildViewBrowserItems(effectiveGraph, changeSummary) : null), [changeSummary, effectiveGraph]);
  const browserSearchState = useMemo(() => buildBrowserSearchState(browserTree, search), [browserTree, search]);

  useEffect(() => {
    if (!flowModel || !selection) {
      return;
    }
    if (selection.kind === 'node' && !flowModel.nodes.some((node) => node.id === selection.id)) {
      setSelection(null);
    }
    if (selection.kind === 'edge' && !flowModel.edges.some((edge) => edge.id === selection.id)) {
      setSelection(null);
    }
  }, [flowModel, selection]);

  useEffect(() => {
    if (!search.trim()) {
      return;
    }
    setExpandedBrowserIds((current) => {
      const next = new Set([...current, ...browserSearchState.expandedKeys]);
      if (next.size === current.size) {
        return current;
      }
      return next;
    });
  }, [browserSearchState, search]);

  if (loadingError) {
    return html`
      <main className="viewer-shell error-shell">
        <section className="panel error-panel">
          <span className="eyebrow">加载失败</span>
          <h1>架构拓扑页面启动失败</h1>
          <p>${loadingError}</p>
        </section>
      </main>
    `;
  }

  if (!flowModel || !graph || !schema) {
    return html`
      <main className="viewer-shell loading-shell">
        <section className="panel boot-card">
          <div className="boot-logo">AF</div>
          <h1>正在准备架构拓扑</h1>
          <p>正在从当前 skill server 获取 Schema 和架构 JSON。</p>
        </section>
      </main>
    `;
  }

  const scopedView = flowModel.scope.scopeView;
  const structuralRoot = (graph.views || []).find((view) => !view.parent_element_id);
  const selectedLabel = selection?.kind === 'node'
    ? flowModel.indexes.elementById.get(selection.id)?.name
    : selection?.kind === 'edge'
      ? flowModel.indexes.relationshipById.get(selection.id)?.name || flowModel.indexes.relationshipById.get(selection.id)?.statement
      : '未选择对象';

  return html`
    <main className="viewer-shell viewer-workbench">
      <header className="app-topbar">
        <div className="app-topbar__left">
          <div className="app-brand-lockup">
            <div className="app-logo" aria-hidden="true">
              <span className="app-logo__core"></span>
              <span className="app-logo__wing app-logo__wing--left"></span>
              <span className="app-logo__wing app-logo__wing--right"></span>
            </div>
            <div className="app-brand-copy">
              <strong>Argo</strong>
              <span className="app-brand-pill">Draft</span>
            </div>
          </div>
        </div>
        <div className="app-topbar__center">
          <label className="toolbar-field toolbar-field--search app-topbar__search">
            <span>查找</span>
            <input
              type="search"
              value=${search}
              onInput=${(event) => setSearch(event.target.value)}
              placeholder="输入您想查找的内容"
              aria-label="输入您想查找的内容"
            />
          </label>
        </div>
        <div className="app-topbar__meta">
          <span className="topbar-pill">${graph.views.length} Views</span>
          <span className="topbar-pill">${flowModel.metrics.totalElements} Nodes</span>
          <span className="topbar-pill ${validationErrors.length === 0 ? 'is-ok' : 'is-warn'}">${validationErrors.length === 0 ? 'Schema OK' : `${validationErrors.length} Issues`}</span>
          <button type="button" className="topbar-action">Share</button>
        </div>
      </header>

      <section
        className="workspace-grid workbench-grid"
        style=${isCompactLayout ? undefined : { gridTemplateColumns: `${leftDockWidth}px 12px minmax(0, 1fr)` }}
      >
        <section ref=${leftDockRef} className="left-dock" style=${isCompactLayout ? undefined : { width: `${leftDockWidth}px` }}>
          <aside className="sidebar panel">
            <${ViewBrowser}
              tree=${browserTree}
              expandedIds=${expandedBrowserIds}
              matchedKeys=${browserSearchState.matchedKeys}
              selectedViewId=${selectedViewId}
              selectedNodeId=${selection?.kind === 'node' ? selection.id : null}
              selectedEdgeId=${selection?.kind === 'edge' ? selection.id : null}
              onToggle=${toggleBrowserNode}
              onSelectView=${openSubview}
              onSelectElement=${openElementFromBrowser}
              onSelectRelationship=${openRelationshipFromBrowser}
            />
          </aside>
        </section>

        ${isCompactLayout ? null : html`
          <div
            ref=${bindWorkspaceDividerRef}
            className=${`workspace-divider${leftDockResizing ? ' is-active' : ''}`}
            role="separator"
            aria-orientation="vertical"
            aria-label="调整浏览器面板宽度"
          ></div>
        `}

        <section ref=${stageShellRef} className="stage-shell">
          <${GraphCanvas}
            flowModel=${flowModel}
            selection=${selection}
            setSelection=${setSelection}
            layoutDirection=${layoutDirection}
            onNodeDragStop=${handleNodeDragStop}
          />

          <${DetailsDrawer}
            selection=${selection}
            flowModel=${flowModel}
            schema=${schema}
            anchorRef=${stageShellRef}
          />
        </section>
      </section>
    </main>
  `;
}

const root = createRoot(document.getElementById('app'));
root.render(html`<${ReactFlowProvider}><${App} /></${ReactFlowProvider}>`);
