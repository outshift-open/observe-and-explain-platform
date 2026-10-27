# Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
# SPDX-License-Identifier: Apache-2.0
"""Prospective structural projection of saved LLM artifacts; no text matching."""
from copy import deepcopy
import json

SEMANTIC = {'Claim', 'Evidence', 'ToolResult', 'Intent', 'Task', 'Constraint', 'SystemPrompt'}
FAMILIES = {
    'Policy Safety': {'Constraint', 'SystemPrompt'},
    'Delegation Accuracy': {'Intent', 'Task', 'Constraint', 'SystemPrompt'},
    'Goal Alignment': {'Intent', 'Task', 'Claim', 'Constraint', 'SystemPrompt'},
    'Communication Efficiency': {'Intent', 'Task', 'Constraint', 'SystemPrompt'},
    **{m: SEMANTIC for m in ('Instruction Following', 'Handoff Quality',
        'Semantic Consistency', 'Context Preservation', 'Confidence Calibration',
        'Verification Quality', 'Groundedness', 'Task Completion',
        'Constraint Satisfaction', 'DecisionCorrectness')},
}
FULL_SOURCE_COVERAGE = {'Handoff Quality', 'Context Preservation', 'Communication Efficiency'}
STATE_METRICS = {
    'Instruction Following', 'Handoff Quality', 'Semantic Consistency',
    'Context Preservation', 'Confidence Calibration', 'Verification Quality',
    'Groundedness', 'Task Completion', 'Constraint Satisfaction',
    'DecisionCorrectness',
}

def anchors(record):
    return [a for a in record.get('anchors', []) if a.get('source_id')]

def slim_anchor(anchor):
    return {k: deepcopy(anchor[k]) for k in ('source_id', 'start', 'end', 'occurrence') if k in anchor}


def slim_record(record):
    """Retain semantics and exact source locations without repeated quotations."""
    return {**{k: deepcopy(v) for k, v in record.items()
               if k not in {'anchors', 'artifact_id', 'first_seen', 'last_seen'}},
            'anchors': [slim_anchor(a) for a in anchors(record)]}


def reasoning_closure(graph, selected, metric):
    """Follow declared IDs, never infer a relationship from prose or names."""
    by_id = {n['id']: n for n in graph.get('nodes', [])}
    values = {v['id']: v for v in graph.get('state_values', [])}
    checks = {c['id']: c for c in graph.get('checks', [])}
    selected_values, selected_checks = set(), set()
    if metric in STATE_METRICS:
        selected_values = {i for i, row in values.items()
            if row.get('task_id') in selected
            or any(p in selected for p in row.get('proposition_ids', []))}
        selected_checks = {i for i, row in checks.items()
            if any(t in selected for t in row.get('target_ids', []))
            or any(p in selected for p in row.get('proposition_ids', []))
            or any(s in selected_values for s in row.get('state_ids', []))}
    while True:
        before = (set(selected), set(selected_values), set(selected_checks))
        for i in tuple(selected):
            parent = by_id[i].get('parent_id')
            if parent in by_id:
                selected.add(parent)
        # Material statements under newly reached parents stay together.
        selected |= {n['id'] for n in by_id.values()
            if n.get('type') == 'Proposition' and n.get('parent_id') in selected}
        for i in tuple(selected_values):
            row = values[i]
            selected |= {p for p in row.get('proposition_ids', []) if p in by_id}
            if row.get('task_id') in by_id:
                selected.add(row['task_id'])
            selected_values |= {p for p in row.get('supersedes', []) if p in values}
        for i in tuple(selected_checks):
            row = checks[i]
            selected |= {p for field in ('target_ids', 'proposition_ids')
                         for p in row.get(field, []) if p in by_id}
            selected_values |= {p for p in row.get('state_ids', []) if p in values}
            selected_checks |= {p for p in row.get('supersedes', []) if p in checks}
        if before == (selected, selected_values, selected_checks):
            break
    return selected, [v for v in graph.get('state_values', []) if v['id'] in selected_values], [
        c for c in graph.get('checks', []) if c['id'] in selected_checks]


def missing_source_groups(records, groups, source_spans):
    """Resolve accepted anchors omitted from the compact recorded-source catalog."""
    available = {o['source_id'] for group in groups for o in group.get('occurrences', [])}
    required = {a['source_id']: a for record in records for a in anchors(record)
                if a['source_id'] not in available}
    if required and source_spans is None:
        raise ValueError('Native source_spans are required for uncatalogued graph anchors: '
                         + ', '.join(sorted(required)))
    result = []
    for source_id, anchor in sorted(required.items()):
        location = anchor.get('source_ref', {})
        index, path = location.get('span_index'), location.get('path')
        if type(index) is not int or not 0 <= index < len(source_spans) or not isinstance(path, list):
            raise ValueError(f'Invalid accepted source location for {source_id}')
        span = source_spans[index]
        value = span
        for part in path:
            if isinstance(value, str):
                value = json.loads(value)
            value = value[part]
        content = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
        occurrence = {'source_id': source_id, 'span_index': index}
        # Inherit only unambiguous recorded annotations for this exact carrier.
        related = [o for group in groups for o in group.get('occurrences', [])
                   if o.get('span_index') == index
                   and (o.get('source_ref', {}).get('path', [])[:len(path)] == path
                        or path[:len(o.get('source_ref', {}).get('path', []))]
                           == o.get('source_ref', {}).get('path', []))]
        for field in ('agent_id', 'message_role', 'direction'):
            candidates = {o[field] for o in related if isinstance(o.get(field), str) and o[field]}
            if len(candidates) == 1:
                occurrence[field] = next(iter(candidates))
        if isinstance(value, dict) and isinstance(value.get('role'), str):
            occurrence['message_role'] = value['role']
        attrs = span.get('SpanAttributes', {})
        if not occurrence.get('agent_id') and isinstance(attrs, dict) and attrs.get('mas.agent.id'):
            occurrence['agent_id'] = attrs['mas.agent.id']
        if span.get('Timestamp'):
            occurrence['recorded_at'] = span['Timestamp']
        result.append({'content': content, 'occurrences': [occurrence]})
    return result

def selected_id_refs(value, valid_ids):
    if isinstance(value, str):
        return {value} if value in valid_ids else set()
    if isinstance(value, dict):
        return set().union(*(selected_id_refs(v, valid_ids) for v in value.values()), set())
    if isinstance(value, list):
        return set().union(*(selected_id_refs(v, valid_ids) for v in value), set())
    return set()

def focus_context(context, metric, *, source_spans=None):
    """Keep source text exact; discard redundant record representations/metadata."""
    graph = context.get('reasoning_graph', {})
    nodes = graph.get('nodes', [])
    by_id = {n['id']: n for n in nodes}
    groups = context.get('recorded_sources', [])
    valid_sources = {o['source_id'] for g in groups for o in g.get('occurrences', [])}
    selected = {n['id'] for n in nodes if n.get('type') in FAMILIES[metric]}
    # A proposition is selected through its typed parent, never its wording.
    selected |= {n['id'] for n in nodes if n.get('type') == 'Proposition'
                 and n.get('parent_id') in selected}
    # Preserve both endpoints of every incident relation, independent of its label.
    if metric != 'Policy Safety':
        incident = [e for e in graph.get('edges', [])
                    if e.get('from_id') in selected or e.get('to_id') in selected]
        neighbors = {e.get(k) for e in incident for k in ('from_id', 'to_id')}
        selected |= {i for i in neighbors if i in by_id}
    selected |= {n['id'] for n in nodes if n.get('type') == 'Proposition'
                 and n.get('parent_id') in selected}
    # Always retain all extracted conditions/exceptions and original instructions.
    selected |= {n['id'] for n in nodes if n.get('type') in {'SystemPrompt', 'Constraint'}}
    selected, state_values, checks = reasoning_closure(graph, selected, metric)
    source_ids = {a['source_id'] for i in selected for a in anchors(by_id[i])}
    source_ids |= {a['source_id'] for row in [*state_values, *checks] for a in anchors(row)}
    for group in groups:
        for occurrence in group.get('occurrences', []):
            if occurrence.get('message_role') in {'system', 'developer'}:
                source_ids.add(occurrence['source_id'])
    edges = [e for e in graph.get('edges', [])
             if e.get('from_id') in selected and e.get('to_id') in selected]
    source_ids |= {a['source_id'] for e in edges for a in anchors(e)}
    added_sources = missing_source_groups(
        [*(by_id[i] for i in selected), *edges, *state_values, *checks], groups, source_spans)
    groups = [*groups, *added_sources]
    valid_sources |= {o['source_id'] for group in added_sources for o in group['occurrences']}

    # For task-level judgments retain original requester premises independently
    # of extraction coverage. User-role sources may be delegated turns.
    if metric != 'Policy Safety':
        source_ids |= {o['source_id'] for g in groups for o in g.get('occurrences', [])
                       if o.get('message_role') == 'user'}
    # Sparse receipt/use links cannot justify omitting communication evidence.
    if metric in FULL_SOURCE_COVERAGE:
        source_ids |= valid_sources
    # Missing node families cause a conservative source fallback, not absence.
    requested = FAMILIES[metric] - {'SystemPrompt', 'Constraint'}
    missing = sorted(t for t in requested if not any(n.get('type') == t for n in nodes))
    if metric != 'Policy Safety' and missing:
        source_ids |= valid_sources

    slim_nodes = []
    for node in nodes:
        if node['id'] not in selected:
            continue
        item = {k: deepcopy(v) for k, v in node.items()
                if k not in {'anchors', 'artifact_id', 'first_seen', 'last_seen'}}
        # Whole parent prose already exists in the exact linked source body.
        if node.get('type') in {'Claim', 'Evidence', 'ToolResult', 'SystemPrompt'}:
            has_children = any(n.get('parent_id') == node['id'] for n in nodes)
            if has_children and anchors(node):
                item.pop('text', None)
        item['anchors'] = [slim_anchor(a) for a in anchors(node)]
        slim_nodes.append(item)
    slim_edges = [slim_record(e) for e in edges]
    source_groups = []
    for group in groups:
        if not any(o['source_id'] in source_ids for o in group.get('occurrences', [])):
            continue
        # Retain the complete source and each occurrence's attribution. Native
        # paths, duplicate telemetry fields and highlight offsets stay in archive.
        source_groups.append({'content': deepcopy(group['content']),
            'occurrences': [{k: deepcopy(o[k]) for k in
                ('source_id', 'span_index', 'agent_id', 'message_role', 'direction', 'recorded_at') if k in o}
                for o in group['occurrences']]})
    result = {'metric_name': metric, 'reasoning_graph': {
        'nodes': slim_nodes, 'edges': slim_edges,
        'state_values': [slim_record(v) for v in state_values],
        'checks': [slim_record(c) for c in checks]},
        'recorded_sources': source_groups}
    if metric != 'Policy Safety':
        inventory = []
        sources_by_span = {}
        for group in source_groups:
            for o in group['occurrences']:
                sources_by_span.setdefault(o.get('span_index'), set()).add(o['source_id'])
        operation_rows = context.get('operations', context.get('actor_scoped_operations', []))
        coarse = {o.get('artifact_id'): o for o in operation_rows}
        for carrier in context.get('recorded_operation_carriers', {}).get('operations', []):
            opid = carrier['operation_id']
            op = coarse.get(opid, {})
            inventory.append({'artifact_id': opid, 'operation_id': opid,
                'span_index': carrier['span_index'],
                'recorded_envelope': deepcopy(carrier.get('recorded_envelope', {})),
                'recorded_attributes': deepcopy(carrier.get('recorded_attributes', {})),
                'source_ids': sorted(sources_by_span.get(carrier['span_index'], set())),
                **{k: deepcopy(op[k]) for k in ('agent_id', 'actor_scope', 'entity_name',
                    'operation_type', 'is_delegation', 'outcome') if k in op}})
        result['operations'] = inventory
    # Retain explicit ownership/routing links without duplicate response bodies.
    for field in ('intents', 'work_units', 'work_assignments', 'delegation_requests',
                  'coordination_events', 'coordination_context'):
        if field in context and metric != 'Policy Safety':
            result[field] = deepcopy(context[field])
    for field in ('policy', 'policy_artifact_id', 'semantic_contracts',
                  'final_answer', 'final_answer_artifact_id', 'final_answer_span_index'):
        if field in context and (metric != 'Policy Safety' or field.startswith('policy') or field == 'semantic_contracts'):
            result[field] = deepcopy(context[field])
    if metric == 'DecisionCorrectness':
        for field in ('root_request', 'root_agent_id', 'tool_definitions'):
            if field in context:
                result[field] = deepcopy(context[field])
    return result, {'families': sorted(FAMILIES[metric]), 'missing_families': missing,
        'full_source_fallback': metric in FULL_SOURCE_COVERAGE or (bool(missing) and metric != 'Policy Safety'),
        'original_nodes': len(nodes), 'selected_nodes': len(slim_nodes),
        'original_state_values': len(graph.get('state_values', [])),
        'selected_state_values': len(state_values),
        'original_checks': len(graph.get('checks', [])), 'selected_checks': len(checks),
        'resolved_uncatalogued_sources': len(added_sources),
        'original_source_groups': len(context.get('recorded_sources', [])),
        'selected_source_groups': len(source_groups),
        'original_source_occurrences': sum(len(g['occurrences'])
            for g in context.get('recorded_sources', [])),
        'selected_source_occurrences': sum(len(g['occurrences']) for g in source_groups)}


def select_metric_context(context, metric, *, source_spans=None):
    """Project accepted graph artifacts; leave legacy/custom contexts unchanged."""
    graph = context.get('reasoning_graph')
    if metric not in FAMILIES or not isinstance(graph, dict) or not graph.get('nodes'):
        return deepcopy(context), {'projection': 'unchanged'}
    return focus_context(context, metric, source_spans=source_spans)
