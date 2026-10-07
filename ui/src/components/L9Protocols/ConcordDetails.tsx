/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { Stack, Typography } from '@mui/material';
import { Banner } from '@open-ui-kit/core';
import {
  CONCORD_PHASE_ORDER,
  L9_CONCORD,
  isBestEffortState,
  isCommitState
} from '@/common/l9Protocols';
import { L9ConcordProtocol } from '@/types/oxp.type';
import { BoundsTable, PhaseUsageTable, UsageSummaryTable } from './UsageTables';
import { SatisfactionTrajectoryChart } from './SatisfactionTrajectoryChart';
import {
  BlockTitle,
  CheckResult,
  MetricRow,
  NotAvailable,
  PassFailTag,
  StatusTag,
  SimpleTable,
  SubSection,
  VerdictResult,
  formatScore
} from './primitives';

const Compliance = ({ protocol }: { protocol: L9ConcordProtocol }) => {
  const compliance = protocol.compliance;
  const completion = compliance?.completion;

  return (
    <SubSection title="Compliance">
      <Stack direction="column" gap="8px">
        <MetricRow
          label="Candidate completeness"
          description="Are all proposals from the different agents taken into account in the decision process?"
        >
          <CheckResult check={compliance?.candidateCompleteness} />
        </MetricRow>
        <MetricRow
          label="Protocol completion"
          description="Did the negotiation reach COMMIT or BEST_EFFORT?"
        >
          {completion ? (
            <Stack direction="row" gap="8px" alignItems="center">
              <PassFailTag passed={completion.passed} />
              <StatusTag
                label={
                  completion.terminalState
                    ? completion.terminalState
                    : 'Neither COMMIT nor BEST_EFFORT'
                }
                tone={
                  isCommitState(completion.terminalState)
                    ? 'positive'
                    : isBestEffortState(completion.terminalState)
                      ? 'warning'
                      : completion.terminalState
                        ? 'info'
                        : 'negative'
                }
              />
            </Stack>
          ) : (
            <NotAvailable />
          )}
        </MetricRow>
        <MetricRow
          label="Protocol compliance"
          description="Did the agents correctly follow the protocol, executing every required step?"
        >
          <CheckResult
            check={compliance?.protocolCompliance}
            failuresLabel="Failed steps"
          />
        </MetricRow>
      </Stack>
    </SubSection>
  );
};

const Correctness = ({ protocol }: { protocol: L9ConcordProtocol }) => (
  <SubSection title="Correctness">
    <Stack direction="column" gap="8px">
      <MetricRow
        label="Outcome satisfaction"
        description="Given what each agent said it needed and why, is the final outcome one it can genuinely live with, rather than one it was merely scored into accepting?"
      >
        <VerdictResult verdict={protocol.correctness?.outcomeSatisfaction} />
      </MetricRow>
      <MetricRow
        label="Score fairness"
        description="Are each agent's raw scores across candidates consistent with that same agent's stated reasoning: an honest, consistent application of its own criteria, or drift and contradiction?"
      >
        <VerdictResult verdict={protocol.correctness?.scoreFairness} />
      </MetricRow>
    </Stack>
  </SubSection>
);

const Cost = ({ protocol }: { protocol: L9ConcordProtocol }) => (
  <SubSection title="Cost">
    <Stack direction="column" gap="16px">
      <UsageSummaryTable usage={protocol.cost?.usage} />
      <Stack direction="column" gap="4px">
        <Typography variant={'body2Semibold'}>Per phase</Typography>
        <PhaseUsageTable
          phases={protocol.cost?.phases}
          phaseOrder={CONCORD_PHASE_ORDER}
        />
      </Stack>
      <Stack direction="column" gap="4px">
        <BlockTitle
          title="Cost vs. ceiling"
          description="What the run used, against the maximum the protocol reported when the run opened. The ceilings (rounds, options generated, agent evaluations, model calls) are exact bounds known before the first call, not estimates. A value equal to its bound means that budget was fully used."
        />
        <BoundsTable bounds={protocol.cost?.bounds} />
      </Stack>
    </Stack>
  </SubSection>
);

const Outcome = ({ protocol }: { protocol: L9ConcordProtocol }) => {
  const outcome = protocol.outcome;
  const tau = outcome?.tau;
  const terminalState = protocol.compliance?.completion?.terminalState;

  const trajectory = outcome?.trajectory ?? [];
  const hasTrajectory = trajectory.some((p) => p.worstAgentScore !== null);
  const agentScores = outcome?.agentScores ?? [];

  return (
    <SubSection title="Outcome">
      <Stack direction="column" gap="20px">
        {isCommitState(terminalState) && (
          <Typography variant={'caption'}>
            {`${terminalState} means every agent cleared the floor. It certifies agreement, not correctness.`}
          </Typography>
        )}

        {isBestEffortState(terminalState) &&
          (outcome?.shortfall ? (
            <Banner
              status="warning"
              text={`BEST_EFFORT: ${outcome.shortfall.agent} is short by ${formatScore(
                outcome.shortfall.shortBy
              )}${
                typeof tau === 'number'
                  ? ` relative to the floor τ = ${formatScore(tau)}`
                  : ''
              }.`}
            />
          ) : (
            <Banner
              status="warning"
              text="BEST_EFFORT: no shortfall data is available."
            />
          ))}

        <Stack direction="column" gap="8px">
          <BlockTitle
            title="Satisfaction trajectory"
            description="The satisfaction of the worst-off agent after each round. Round 0 is the seed, where every agent proposes one starting option. After that, one new option is added per round, written by the agent the current leading option serves worst, and the whole pool is re-ranked. The line rises as the worst-off agent improves. The run commits once it reaches τ, or ends in BEST_EFFORT when the round budget runs out."
          />
          {hasTrajectory ? (
            <>
              <SatisfactionTrajectoryChart trajectory={trajectory} tau={tau} />
              {typeof tau !== 'number' && (
                <Typography variant={'caption'}>
                  The floor threshold τ is not available.
                </Typography>
              )}
            </>
          ) : (
            <NotAvailable text="No data" />
          )}
        </Stack>

        <Stack direction="column" gap="8px">
          <BlockTitle
            title={`Final satisfaction per agent${
              typeof tau === 'number' ? ` (τ = ${formatScore(tau)})` : ''
            }`}
            description="Each agent's satisfaction with the final outcome, expressed relative to its own two reference points (what 'unacceptable' and 'fully satisfied' look like for the task), so scores are comparable across agents. τ is the satisfaction floor: the protocol commits only when every agent is at or above it, otherwise it ends in BEST_EFFORT and reports the shortfall. τ is configured for the protocol and must be calibrated for the use case: set too low, an initial proposal already clears it and no repair round runs. It does not move during a run."
          />
          {agentScores.length === 0 ? (
            <NotAvailable text="No data" />
          ) : (
            <SimpleTable
              headers={['Agent', 'Satisfaction', 'Versus τ']}
              rows={agentScores.map((agent) => [
                agent.agent,
                formatScore(agent.score),
                agent.score === null || typeof tau !== 'number' ? (
                  <NotAvailable key="vs" />
                ) : agent.score < tau ? (
                  <StatusTag key="vs" label="Below τ" tone="negative" />
                ) : (
                  <StatusTag key="vs" label="At or above τ" tone="positive" />
                )
              ])}
            />
          )}
        </Stack>
      </Stack>
    </SubSection>
  );
};

export const ConcordDetails = ({
  protocol
}: {
  protocol: L9ConcordProtocol;
}) => (
  <>
    <Compliance protocol={protocol} />
    <Correctness protocol={protocol} />
    <Cost protocol={protocol} />
    <Outcome protocol={protocol} />
  </>
);
