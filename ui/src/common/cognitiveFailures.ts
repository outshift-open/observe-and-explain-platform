/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import ForumOutlinedIcon from '@mui/icons-material/ForumOutlined';
import HubOutlinedIcon from '@mui/icons-material/HubOutlined';
import TaskAltOutlinedIcon from '@mui/icons-material/TaskAltOutlined';
import type { SvgIconComponent } from '@mui/icons-material';

// A failure counts for a session only when its confidence is above this value.
export const FAILURE_CONFIDENCE_THRESHOLD = 0.8;

// Groups of cognitive metrics, shown as columns, in display order.
export const COGNITIVE_METRIC_GROUPS: {
  title: string;
  icon: SvgIconComponent;
  metrics: string[];
}[] = [
  {
    title: 'Coordination structure',
    icon: HubOutlinedIcon,
    metrics: ['Policy Safety', 'Delegation Accuracy', 'Goal Alignment']
  },
  {
    title: 'Interaction quality',
    icon: ForumOutlinedIcon,
    metrics: [
      'Instruction Following',
      'Handoff Quality',
      'Semantic Consistency',
      'Context Preservation',
      'Confidence Calibration',
      'Verification Quality',
      'Communication Efficiency'
    ]
  },
  {
    title: 'Outcome quality',
    icon: TaskAltOutlinedIcon,
    metrics: ['Groundedness', 'Task Completion', 'Constraint Satisfaction']
  }
];

// Explanations of the remediation protocols, keyed by lowercase protocol name.
const COGNITIVE_REMEDIATION_DESCRIPTIONS: Record<string, string> = {
  'l9-accord':
    "A pre-execution, four-phase protocol (CONVENE → FRAME → GROUND → VERIFY) that gets agents to establish shared intent before any work begins: who they are, what problem they're solving, what terms mean, and how correctness will be checked. It produces a locked Intent Contract and is explicitly not negotiation — just identity/capability/semantic reconciliation.",
  'l9-concord':
    'An execution-phase protocol that aggregates agent preferences over a shared model via multi-round leximin negotiation (ANCHOR → PROPOSE_SEED → SCORE → REPAIR → COMMIT), converging on a consensus with a formal CONCORD certificate.'
};

export const getRemediationDescription = (name: string): string | undefined =>
  COGNITIVE_REMEDIATION_DESCRIPTIONS[name.toLowerCase()];

// Explanations of the cognitive failures, keyed by failure name.
export const COGNITIVE_FAILURE_DESCRIPTIONS: Record<string, string> = {
  'Task Decomposition and Role Allocation Failure':
    'The team fails to break the task into the right subtasks or assign them to the right agents.',
  'Collective Goal Coordination Failure':
    "Agents don't jointly balance multiple global objectives, over-optimizing one at the expense of others.",
  'Incomplete Synthesis':
    'The final answer omits or fails to integrate parts that different agents contributed.',
  'Situational State Synchronisation Failure':
    "A changed situational fact isn't propagated, so agents act on inconsistent world state.",
  'Shared Task Model Failure':
    'Agents pursue conflicting objectives because they lack a common understanding of the goal (divergent goals).',
  'Shared State Degradation':
    "A fact that changed mid-task isn't updated, so agents keep using a stale/superseded value.",
  'Verification and Epistemic Control Failure':
    'The system skips checking/verification and commits a confident but unverified result.',
  'Communication Policy Inefficiency':
    'Agents communicate wastefully (too verbose/exhaustive), producing low-signal, degraded coordination.',
  'Illocutionary Misidentification':
    'An agent misreads the intent or force of a message (e.g., treats a hard constraint as optional).',
  'Negotiation and Consensus Failure':
    "Agents can't resolve a disagreement into a single coherent decision.",
  'Task Delegation Failure':
    'Work is handed to an agent that lacks the right capability for it (wrong capability).',
  'Semantic and Ontological Misalignment':
    'Agents interpret the same term or concept differently (meaning mismatch).',
  'Representational Fidelity Loss at Interface':
    'Information is degraded or dropped when summarized/passed across a handoff.',
  'Transactive Memory Failure':
    'The team mismanages who-knows-what or the ordering of knowledge (e.g., needs info before it exists).',
  'Collective Reasoning Degradation':
    "The group's combined reasoning is worse than an individual's (e.g., a wrong premise propagates).",
  'Unformalized Coordination Commitments':
    'Agents rely on unstated/assumed agreements instead of explicit checks, so things slip through.',
  'Intention Stability Failure':
    'An agent drifts from its committed goal when tempted by distracting alternatives.',
  'Plan Revision Failure':
    'An agent fails to update its plan when tools or evidence contradict its assumptions.',
  'Individual Metacognitive Blindness':
    'An agent is overconfident and unaware of its own knowledge limits (answers without the needed lookup).',
  'Individual Representational Failure':
    "An agent misrepresents the task's own constraints/requirements (e.g., botches a checklist's units/exclusions/ordering)."
};
